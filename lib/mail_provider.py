"""Mail automation using opaque selectors and private JSON stdin."""

import json
import os
import sqlite3
import subprocess
from pathlib import Path

from productivity_contract import (
    check_revision,
    create_once,
    digest,
    fail,
    paginate,
    timestamp,
)

JXA = r"""
const app=Application('Mail');ObjC.import('AppKit');
function session(){const apps=$.NSRunningApplication.runningApplicationsWithBundleIdentifier('com.apple.mail');if(!apps.count)error('not_found','Mail is not running');return String(apps.objectAtIndex(0).launchDate.timeIntervalSince1970);}

function error(code,message){throw {code,message};}
function encode(kind,value){return kind+':'+encodeURIComponent(JSON.stringify(value));}
function decode(kind,value){try {if(!value.startsWith(kind+':'))throw 0;return JSON.parse(decodeURIComponent(value.slice(kind.length+1)));}catch(e){error('invalid_argument','Invalid '+kind+' ID');}}
function iso(d){return d?d.toISOString():null;}
function account(id){const a=app.accounts.byId(id);if(!a.exists())error('not_found','Mail account ID no longer exists');return a;}
function boxes(){
 const rows=[],seen={};
 function walk(b,accountId,path,parent){
  const names=path.concat([b.name()]),id=encode('mailbox',[accountId,names]);if(seen[id])return;seen[id]=true;
  rows.push({object:b,id,title:b.name(),account_id:accountId,parent_id:parent});
  b.mailboxes().forEach(x=>walk(x,accountId,names,id));
 }
 app.accounts().forEach(a=>a.mailboxes().forEach(b=>walk(b,a.id(),[],null)));
 app.mailboxes().forEach(b=>{let a=null;try{a=b.account().id();}catch(e){}if(a!==null)return;walk(b,null,[],null);});
 return rows;
}
function box(id){const b=boxes().find(b=>b.id===id);if(!b)error('not_found','Mailbox moved or no longer exists; rediscover');return b;}
function recipients(m,key){return m[key]().map(r=>r.address());}
function messageRow(m,b,full){
 const r={id:encode('message',[b.id,m.id()]),mailbox_id:b.id,subject:m.subject()||'',sender:m.sender()||'',received_at:iso(m.dateReceived()),read:m.readStatus()};
 if(full){r.body_text=String(m.content());r.to=recipients(m,'toRecipients');r.cc=recipients(m,'ccRecipients');r.bcc=recipients(m,'bccRecipients');r.attachment_count=m.mailAttachments().length;}
 return r;
}
function draft(id){const pair=decode('draft',id);if(pair[0]!==session())error('not_found','Draft belongs to a previous Mail session; rediscover');const m=app.outgoingMessages.byId(pair[1]);if(!m.exists())error('not_found','Compose draft closed or no longer exists; rediscover');return m;}
function draftRow(m){return {id:encode('draft',[session(),m.id()]),subject:m.subject()||'',body_text:String(m.content()),sender:m.sender()||'',to:recipients(m,'toRecipients'),cc:recipients(m,'ccRecipients'),bcc:recipients(m,'bccRecipients'),visible:m.visible()};}
function patch(m,p){
 if(p.account_id!==undefined){const a=account(p.account_id),addresses=a.emailAddresses();if(!addresses.length)error('invalid_argument','Selected account has no sender address');m.sender=addresses[0];}
 if(p.subject!==undefined)m.subject=p.subject;

 for(const pair of [['to','toRecipients','ToRecipient'],['cc','ccRecipients','CcRecipient'],['bcc','bccRecipients','BccRecipient']]){
  if(p[pair[0]]!==undefined){m[pair[1]]().forEach(r=>app.delete(r));p[pair[0]].forEach(address=>m[pair[1]].push(app[pair[2]]({address})));}
 }

 if(p.visible!==undefined && p.body_text===undefined)m.visible=p.visible;
}
let phase=operation;
try{
 let result;
 if(operation==='mail_verify_draft_deleted'){
  const ids=app.draftsMailbox.messages.id();result={deleted:ids.indexOf(input.saved_message_id)<0||app.draftsMailbox.messages.byId(input.saved_message_id).deletedStatus()};
 }
 else if(operation==='mail_list_accounts')result=app.accounts().map(a=>({id:a.id(),name:a.name(),addresses:a.emailAddresses()}));
 else if(operation==='mail_list_mailboxes') {if(input.account_id)account(input.account_id);result=boxes().filter(b=>!input.account_id||b.account_id===input.account_id).map(b=>({id:b.id,title:b.title,account_id:b.account_id,parent_id:b.parent_id}));}
 else if(operation==='mail_list_messages'||operation==='mail_search_messages'){
  if(input.account_id)account(input.account_id);
  const chosen=input.mailbox_id?[box(input.mailbox_id)]:boxes().filter(b=>!input.account_id||b.account_id===input.account_id);
  if(input.account_id && chosen.some(b=>b.account_id!==input.account_id))error('invalid_argument','Mailbox does not belong to selected account');
  result=[];
  for(const b of chosen){
   let messages=b.object.messages;
   if(input.query)messages=messages.whose({_or:[{subject:{_contains:input.query}},{sender:{_contains:input.query}}]});
   if(input.received_from)messages=messages.whose({dateReceived:{_greaterThan:new Date(new Date(input.received_from).getTime()-1)}});
   messages().forEach(m=>{
    if(m.deletedStatus())return;
    const r=messageRow(m,b,false),t=r.received_at?new Date(r.received_at).getTime():null;
    if(input.received_from && (t===null||t<new Date(input.received_from).getTime()))return;
    if(input.received_to && (t===null||t>=new Date(input.received_to).getTime()))return;
    if(input.unread!==undefined && (!r.read)!==input.unread)return;
    if(input.query && !(r.subject+'\n'+r.sender).toLowerCase().includes(input.query.toLowerCase()))return;
    result.push(r);
   });
  }
 }else if(operation==='mail_get_message'){
  const pair=decode('message',input.id),b=box(pair[0]),m=b.object.messages.byId(pair[1]);if(!m.exists()||m.deletedStatus())error('not_found','Message no longer exists in this mailbox');result=messageRow(m,b,true);
 }else if(operation==='mail_list_drafts')result=app.outgoingMessages().map(draftRow);
 else if(operation==='mail_create_draft'){
  if(input.account_id)account(input.account_id);
  const props={subject:input.subject,content:input.body_text,visible:input.visible===undefined?true:input.visible};if(input.sender)props.sender=input.sender;const m=app.OutgoingMessage(props);app.outgoingMessages.push(m);
  patch(m,{...input,body_text:undefined,subject:undefined,visible:input.visible===undefined?true:input.visible});
  app.save(m);result=draftRow(m);
 }else{
  const m=draft(input.id),r=draftRow(m);
  if(operation==='mail_inspect_saved_draft'){
    const copies=app.draftsMailbox.messages.whose({subject:r.subject}).id().map(id=>app.draftsMailbox.messages.byId(id));
    const matches=copies.filter(c=>!c.deletedStatus() && String(c.content()).trim()===r.body_text.trim() && JSON.stringify(recipients(c,'toRecipients'))===JSON.stringify(r.to) && JSON.stringify(recipients(c,'ccRecipients'))===JSON.stringify(r.cc) && JSON.stringify(recipients(c,'bccRecipients'))===JSON.stringify(r.bcc));
    if(!matches.length)error('saved_copy_pending','Saved draft copy has not settled; retry the read');
    if(matches.length!==1)error('ambiguous_draft','Cannot uniquely verify saved draft metadata; wait for sync or use a unique subject');
    const c=matches[0],headers=c.allHeaders();
    result={saved_message_id:c.id(),attachment_count:c.mailAttachments().length,threaded:/^(in-reply-to|references):/im.test(headers)||/^\s*(re|fw|fwd):/i.test(r.subject)};
  }
  else if(operation==='mail_get_draft')result=r;
  else if(operation==='mail_save_draft'){if(!input.confirm||JSON.stringify(r)!==input.expected_snapshot)error('conflict','Draft changed before saving');app.save(m);result=r;}
  else{
   if(!input.confirm)error('confirmation_required','Writing requires confirm=true');
   if(JSON.stringify(r)!==input.expected_snapshot)error('conflict','Draft changed; read it again');
   if(operation==='mail_delete_draft'){
    phase='prepare discard';
    phase='find saved draft copy';const copies=app.draftsMailbox.messages.whose({subject:r.subject}).id().map(id=>app.draftsMailbox.messages.byId(id));
    phase='inspect saved draft copy';const matches=copies.filter(c=>!c.deletedStatus() && String(c.content()).trim()===r.body_text.trim() && JSON.stringify(recipients(c,'toRecipients'))===JSON.stringify(r.to) && JSON.stringify(recipients(c,'ccRecipients'))===JSON.stringify(r.cc) && JSON.stringify(recipients(c,'bccRecipients'))===JSON.stringify(r.bcc));
    if(!matches.length)error('saved_copy_pending','Saved draft copy has not settled; retry the read');
    if(matches.length!==1)error('ambiguous_draft','Cannot uniquely verify the saved draft copy; wait for sync or give this draft a unique subject');
    phase='read saved draft identity';const savedId=matches[0].id();
    phase='discard compose draft';try{app.close(m,{saving:'no'});}catch(e){}app.delete(app.draftsMailbox.messages.byId(savedId));
    result={id:input.id,deleted:true,saved_message_id:savedId};
   }
   else{
    if(input.body_text!==undefined)error('unsupported_operation','Body updates use a verified draft rebuild');
    patch(m,input);
    delay(0.3);result=draftRow(m);
    if(input.visible!==undefined){m.visible=input.visible;result=draftRow(m);}

   }
  }
 }
 JSON.stringify({success:true,data:result});
}catch(e){JSON.stringify({success:false,error:{code:e.code||(e.errorNumber===-1743?'permission_denied':'native_error'),message:phase+': '+(e.message||String(e))}});}
"""


def native(operation, p):
    import time

    from productivity_contract import ContractError

    for attempt in range(10):
        try:
            return native_once(operation, p)
        except ContractError as error:
            if error.error["code"] != "saved_copy_pending" or attempt == 9:
                raise
            time.sleep(0.2)


def native_once(operation, p):
    code = (
        "const operation="
        + json.dumps(operation)
        + ";const input="
        + json.dumps(p, ensure_ascii=False)
        + ";\n"
        + JXA
    )
    try:
        r = subprocess.run(
            ["osascript", "-l", "JavaScript"],
            input=code,
            capture_output=True,
            text=True,
            timeout=110,
        )
    except subprocess.TimeoutExpired:
        fail(
            "timeout"
            if operation
            in {
                "mail_list_accounts",
                "mail_list_mailboxes",
                "mail_list_messages",
                "mail_search_messages",
                "mail_get_message",
                "mail_list_drafts",
                "mail_get_draft",
            }
            else "outcome_unknown",
            "Mail automation timed out",
            "Read/search before retrying a write",
        )
    if r.returncode:
        fail(
            "permission_denied" if "-1743" in r.stderr else "native_error",
            "Mail automation failed",
            "Allow the host to automate Mail",
        )
    try:
        response = json.loads(r.stdout)
    except ValueError:
        fail("native_error", "Mail returned invalid JSON")
    if not response.get("success"):
        e = response.get("error", {})
        code = e.get("code", "native_error")
        fail(
            code,
            e.get("message", "Mail operation failed"),
            "Read the item again or check Mail permissions",
            write_not_started=code
            in {
                "not_found",
                "invalid_argument",
                "conflict",
                "confirmation_required",
                "attachments_present",
                "attachment_check_unavailable",
                "permission_denied",
                "ambiguous_draft",
                "saved_copy_pending",
            },
        )
    return response["data"]


def revision(row):
    return {**row, "revision": digest(row)}


def deleted_drafts(identifier=None):
    path = (
        Path(
            os.environ.get(
                "MACOS_MCP_STATE_DIR", "~/Library/Application Support/zyx1121/macos"
            )
        ).expanduser()
        / "requests.sqlite3"
    )
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with sqlite3.connect(path) as db:
        os.chmod(path, 0o600)
        db.execute("CREATE TABLE IF NOT EXISTS deleted_drafts (id TEXT PRIMARY KEY)")
        if identifier is not None:
            db.execute("INSERT OR IGNORE INTO deleted_drafts VALUES (?)", (identifier,))
        return {r[0] for r in db.execute("SELECT id FROM deleted_drafts")}


def perform(operation, p):
    if p.get("received_from"):
        timestamp(p["received_from"])
    if p.get("received_to"):
        timestamp(p["received_to"])
    if (
        p.get("received_from")
        and p.get("received_to")
        and timestamp(p["received_to"]) <= timestamp(p["received_from"])
    ):
        fail(
            "invalid_argument",
            "received_to must be later than received_from",
            write_not_started=True,
        )
    if operation in {"mail_list_accounts", "mail_list_mailboxes"}:
        return native(operation, p)
    if operation in {"mail_list_messages", "mail_search_messages", "mail_list_drafts"}:
        rows = native(operation, p)
        if operation == "mail_list_drafts":
            deleted = deleted_drafts()
            rows = [revision(r) for r in rows if r["id"] not in deleted]
        rows.sort(key=lambda r: (r.get("received_at") or "", r["id"]), reverse=True)
        return paginate(rows, p)
    if (
        operation in {"mail_get_draft", "mail_update_draft", "mail_delete_draft"}
        and p.get("id") in deleted_drafts()
    ):
        fail(
            "not_found",
            "Draft was discarded in this Mail session",
            write_not_started=True,
        )
    if operation in {"mail_get_message", "mail_get_draft", "mail_create_draft"}:
        result = native(operation, p)
        if operation == "mail_create_draft":
            result = native("mail_get_draft", {"id": result["id"]})
        return revision(result)
    if operation not in {"mail_update_draft", "mail_delete_draft"}:
        fail("invalid_argument", "Unknown Mail operation")
    current = native("mail_get_draft", {"id": p["id"]})
    check_revision(revision(current), p["expected_revision"])
    if operation == "mail_update_draft" and not any(
        k in p
        for k in ("subject", "body_text", "to", "cc", "bcc", "account_id", "visible")
    ):
        fail(
            "invalid_argument", "Update requires changed fields", write_not_started=True
        )
    native(
        "mail_save_draft",
        {
            "id": p["id"],
            "confirm": True,
            "expected_snapshot": json.dumps(
                current, ensure_ascii=False, separators=(",", ":")
            ),
        },
    )
    refreshed = native("mail_get_draft", {"id": p["id"]})
    if refreshed != current:
        check_revision(revision(refreshed), p["expected_revision"])
    if operation == "mail_update_draft" and "body_text" in p:
        return rebuild_draft(refreshed, p)
    result = native(
        operation,
        {
            **p,
            "expected_snapshot": json.dumps(
                refreshed, ensure_ascii=False, separators=(",", ":")
            ),
        },
    )
    if operation == "mail_delete_draft":
        import time

        for _ in range(10):
            if native(
                "mail_verify_draft_deleted",
                {"saved_message_id": result["saved_message_id"]},
            )["deleted"]:
                deleted_drafts(p["id"])
                return {"id": p["id"], "deleted": True}
            time.sleep(0.2)
        fail(
            "outcome_unknown",
            "Saved draft deletion did not settle",
            "Rediscover before retrying",
        )
    import time

    for _ in range(10):
        current = native("mail_get_draft", {"id": p["id"]})
        matches = all(
            (
                current.get(k, "").strip() == v.strip()
                if k in {"body_text", "subject"}
                else current.get(k) == v
            )
            for k, v in p.items()
            if k in {"subject", "body_text", "to", "cc", "bcc", "visible"}
        )
        if matches:
            native(
                "mail_save_draft",
                {
                    "id": p["id"],
                    "confirm": True,
                    "expected_snapshot": json.dumps(
                        current, ensure_ascii=False, separators=(",", ":")
                    ),
                },
            )
            saved = native("mail_get_draft", {"id": p["id"]})
            if all(
                (
                    saved.get(k, "").strip() == v.strip()
                    if k in {"body_text", "subject"}
                    else saved.get(k) == v
                )
                for k, v in p.items()
                if k in {"subject", "body_text", "to", "cc", "bcc", "visible"}
            ):
                return revision(saved)

        time.sleep(0.2)
    fail(
        "native_write_unverified",
        "Mail did not apply the requested fields",
        "Read the current draft before retrying",
    )


def rebuild_draft(current, p):
    info = native("mail_inspect_saved_draft", {"id": p["id"]})
    if info["attachment_count"]:
        fail(
            "attachments_present",
            "Body replacement refuses attachment-bearing drafts",
            write_not_started=True,
        )
    if info["threaded"]:
        fail(
            "unsupported_operation",
            "Body replacement refuses reply/forward drafts to preserve threading",
            write_not_started=True,
        )
    payload = {
        k: p.get(k, current[k])
        for k in ("subject", "body_text", "to", "cc", "bcc", "visible")
    }
    payload["sender"] = current["sender"]
    if p.get("account_id"):
        payload["account_id"] = p["account_id"]
        payload.pop("sender", None)
    payload["request_key"] = "mail-rebuild:" + digest(
        {"id": p["id"], "expected_revision": p["expected_revision"], "patch": p}
    )
    created = create_once(
        "mail_rebuild_draft",
        payload,
        lambda: revision(native("mail_create_draft", payload)),
    )
    try:
        replacement = native("mail_get_draft", {"id": created["id"]})
        if replacement["body_text"].strip() != payload["body_text"].strip() or any(
            replacement[k] != payload[k] for k in ("subject", "to", "cc", "bcc")
        ):
            fail(
                "native_write_unverified",
                "Replacement draft did not match the requested fields",
            )
        original = native("mail_get_draft", {"id": p["id"]})
        check_revision(revision(original), p["expected_revision"])
        result = native(
            "mail_delete_draft",
            {
                "id": p["id"],
                "confirm": True,
                "expected_snapshot": json.dumps(
                    original, ensure_ascii=False, separators=(",", ":")
                ),
            },
        )
        import time

        for _ in range(10):
            if native(
                "mail_verify_draft_deleted",
                {"saved_message_id": result["saved_message_id"]},
            )["deleted"]:
                deleted_drafts(p["id"])
                return {**revision(replacement), "replacement_of": p["id"]}
            time.sleep(0.2)
        fail("outcome_unknown", "Original saved draft deletion did not settle")
    except Exception:
        fail(
            "outcome_unknown",
            "Draft rebuild requires reconciliation; the original may still exist",
            "Inspect both IDs before retrying",
            original_draft_id=p["id"],
            replacement_draft_id=created["id"],
        )
