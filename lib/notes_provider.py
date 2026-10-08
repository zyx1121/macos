"""Notes automation over JXA/Apple Events; JSON passes over stdin, never a shell."""

from __future__ import annotations

import html
import json
import subprocess

from productivity_contract import check_revision, content_html, digest, fail, paginate

JXA = r"""
const app = Application('Notes');
function error(code,message) { throw {code:code,message:message}; }
function iso(d) { return d ? d.toISOString() : null; }
function folderObjects() {
  const result=[],seen={};
  function walk(f,account,parent,accountId) {
    const id=f.id(); if(seen[id]) return; seen[id]=true;
    result.push({object:f,id:id,title:f.name(),account:account,account_id:accountId,parent_id:f.container().id()===accountId?null:f.container().id(),shared:f.shared(),writable:null});
    f.folders.id().forEach(childId=>walk(f.folders.byId(childId),account,id,accountId));
  }
  app.accounts.id().forEach(accountId=>{const a=app.accounts.byId(accountId);a.folders.id().forEach(folderId=>walk(a.folders.byId(folderId),a.name(),null,a.id()));});
  return result;
}
function folder(id) { const f=folderObjects().find(f=>f.id===id); if(!f) error('not_found','Notes folder ID no longer exists'); return f.object; }
function folderRow(id) {
 const f=folderObjects().find(x=>x.id===id);if(!f)error('not_found','Folder ID no longer exists');
 return {id:f.id,title:f.title,account:f.account,account_id:f.account_id,parent_id:f.parent_id,shared:f.shared,writable:null,note_count:f.object.notes().length,folder_count:f.object.folders().length};
}
function account(id) {const a=app.accounts.byId(id);if(!a.exists())error('not_found','Account ID no longer exists');return a;}
function note(id) { const n=app.notes.byId(id); if(!n.exists()) error('not_found','Note ID no longer exists'); return n; }
function row(n) {
  const locked=n.passwordProtected();
  const attachments=locked ? [] : n.attachments().map(a=>({id:a.id(),title:a.name(),content_id:a.contentIdentifier(),url:a.url()}));
  return {id:n.id(),title:n.name(),folder_id:n.container().id(),created_at:iso(n.creationDate()),modified_at:iso(n.modificationDate()),locked:locked,shared:n.shared(),attachment_count:attachments.length,attachments:attachments,
    body_html:locked?'':n.body(),body_text:locked?'':n.plaintext()};
}
function snapshot(r) { return JSON.stringify(r); }
try {
  let result;
  if(operation==='notes_list_accounts') {
    result=app.accounts().map(a=>({id:a.id(),title:a.name()}));
  } else if(['notes_get_folder','notes_create_folder','notes_update_folder','notes_delete_folder'].indexOf(operation)>=0) {
    if(operation==='notes_create_folder') {
      const a=account(input.account_id),parent=input.parent_id?folder(input.parent_id):a;
      if(input.parent_id && folderRow(input.parent_id).account_id!==input.account_id)error('invalid_argument','Parent folder belongs to another account');
      const f=app.Folder({name:input.title});parent.folders.push(f);result=folderRow(f.id());
    } else {
      const f=folder(input.id),r=folderRow(input.id);
      if(operation==='notes_get_folder') result=r;
      else {
        if(!input.confirm)error('confirmation_required','Writing requires confirm=true');
        if(snapshot(r)!==input.expected_snapshot)error('conflict','Folder changed; read it again');
        if(operation==='notes_delete_folder') {
          if(r.note_count || r.folder_count)error('not_empty','Only empty folders can be deleted');
          if(r.parent_id!==null)error('unsupported_operation','Notes does not reliably delete nested folders through Apple Events; use Notes for this folder');
          app.delete(f);
          let remaining=true;
          for(let attempt=0;attempt<10;attempt++){delay(0.1);remaining=folderObjects().some(x=>x.id===input.id);if(!remaining)break;}
          if(remaining)error('outcome_unknown','Folder deletion has not settled; rediscover before retrying');
          result={id:input.id,deleted:true};
        } else {
          if(input.parent_id!==undefined) {
            const dest=folderRow(input.parent_id);if(dest.account_id!==r.account_id)error('invalid_argument','Cross-account folder moves are not supported');
            let ancestor=dest;
            while(ancestor) {if(ancestor.id===r.id)error('invalid_argument','Folder move would create a cycle');ancestor=ancestor.parent_id?folderRow(ancestor.parent_id):null;}
            app.move(f,{to:folder(input.parent_id)});
          }
          if(input.title!==undefined)f.name=input.title;
          result=folderRow(input.id);
        }
      }
    }
  } else if(operation==='notes_list_folders') {
    result=folderObjects().map(f=>({id:f.id,title:f.title,account:f.account,account_id:f.account_id,parent_id:f.parent_id,shared:f.shared,writable:f.writable}));
  } else if(operation==='notes_list'||operation==='notes_search') {
    const ns=input.folder_id ? folder(input.folder_id).notes() : app.notes();
    result=ns.map(row);
  } else if(operation==='notes_create') {
    const f=folder(input.folder_id);
    const n=app.Note({body:input.new_html});f.notes.push(n);result=row(n);
  } else {
    let n=note(input.id),r=row(n);
    if(r.locked) error('locked','Unlock this note in Notes before reading or editing');
    if(operation==='notes_get') result=r;
    else {
      if(!input.confirm) error('confirmation_required','Writing existing notes requires confirm=true');
      if(snapshot(r)!==input.expected_snapshot) error('conflict','Note changed during the operation; read it again');
      if(operation==='notes_delete') { app.delete(n); result={id:input.id,deleted:true}; }
      else {
        if(input.new_html!==undefined && r.attachment_count>0) error('attachments_present','Body edits are refused for notes with attachments');
        if(input.folder_id!==undefined) { const f=folder(input.folder_id); app.move(n,{to:f}); n=note(input.id); }
        if(input.new_html!==undefined) n.body=input.new_html;
        if(input.title!==undefined && input.new_html===undefined) n.name=input.title;
        result=row(n);
      }
    }
  }
  JSON.stringify({success:true,data:result});
} catch(e) {
  JSON.stringify({success:false,error:{code:e.code||((e.errorNumber===-1743)?'permission_denied':'native_error'),message:e.message||String(e)}});
}
"""


def native(operation, p):
    code = (
        "const operation="
        + json.dumps(operation)
        + "; const input="
        + json.dumps(p, ensure_ascii=False)
        + ";\n"
        + JXA
    )
    try:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript"],
            input=code,
            capture_output=True,
            text=True,
            timeout=70,
        )
    except subprocess.TimeoutExpired:
        fail(
            "outcome_unknown"
            if operation
            not in {"notes_list_folders", "notes_list", "notes_search", "notes_get"}
            else "timeout",
            "Notes automation timed out",
            "Read/search before retrying a write",
        )
    if result.returncode:
        fail(
            "permission_denied" if "-1743" in result.stderr else "native_error",
            "Notes automation failed",
            "Allow the MCP host to automate Notes in System Settings",
        )
    try:
        response = json.loads(result.stdout)
    except ValueError:
        fail("native_error", "Notes returned an invalid response")
    if not response.get("success"):
        e = response.get("error", {})
        fail(
            e.get("code", "native_error"),
            e.get("message", "Notes operation failed"),
            "Read the note again or check Notes permissions",
            write_not_started=e.get("code")
            in {
                "not_found",
                "locked",
                "conflict",
                "confirmation_required",
                "attachments_present",
                "not_empty",
                "unsupported_operation",
                "invalid_argument",
                "permission_denied",
            },
        )
    return response["data"]


def with_revision(r):
    result = dict(r)
    result["revision"] = digest(r)
    result["preview"] = r.get("body_text", "")[:240]
    return result


def _perform(operation, p):
    if operation == "notes_list_accounts":
        return native(operation, p)
    if operation in {
        "notes_get_folder",
        "notes_create_folder",
        "notes_update_folder",
        "notes_delete_folder",
    }:
        if operation in {"notes_get_folder", "notes_create_folder"}:
            return with_revision(native(operation, p))
        current = native("notes_get_folder", {"id": p["id"]})
        check_revision(with_revision(current), p["expected_revision"])
        if operation == "notes_update_folder" and not any(
            k in p for k in ("title", "parent_id")
        ):
            fail(
                "invalid_argument",
                "Folder update requires title or parent_id",
                write_not_started=True,
            )
        result = native(
            operation,
            {
                **p,
                "expected_snapshot": json.dumps(
                    current, ensure_ascii=False, separators=(",", ":")
                ),
            },
        )
        return result if operation == "notes_delete_folder" else with_revision(result)
    if operation == "notes_list_folders":
        return native(operation, p)
    if operation in {"notes_list", "notes_search"}:
        rows = [with_revision(r) for r in native(operation, p)]
        needle = p.get("query", "").casefold()
        rows = [
            r for r in rows if needle in (r["title"] + "\n" + r["body_text"]).casefold()
        ]
        rows.sort(key=lambda r: (r["modified_at"] or "", r["id"]), reverse=True)
        summaries = [
            {
                k: v
                for k, v in r.items()
                if k not in {"body_html", "body_text", "attachments"}
            }
            for r in rows
        ]
        return paginate(summaries, p)
    if operation == "notes_create":
        body = content_html(p)
        title = html.escape(p["title"])
        return with_revision(
            native(
                operation, {**p, "new_html": "<div><b>" + title + "</b></div>" + body}
            )
        )
    current = native("notes_get", {"id": p["id"]})
    if operation == "notes_get":
        return with_revision(current)
    if not p.get("confirm"):
        fail(
            "confirmation_required",
            "Writing existing notes requires confirm=true",
            write_not_started=True,
        )
    check_revision(with_revision(current), p["expected_revision"])
    payload = {
        **p,
        "expected_snapshot": json.dumps(
            current, ensure_ascii=False, separators=(",", ":")
        ),
    }
    has_body = "body_text" in p or "body_html" in p
    if operation == "notes_append":
        if not has_body:
            fail(
                "invalid_argument",
                "Append requires body_text or body_html",
                write_not_started=True,
            )
        content = content_html(p)
        # Keep existing native HTML, including lists and formatting. Attachments are checked in JXA.
        old = current["body_html"]
        lower = old.lower()
        index = lower.rfind("</body>")
        payload["new_html"] = (
            old[:index] + content + old[index:] if index >= 0 else old + content
        )
    elif operation == "notes_update":
        if not any(k in p for k in ("title", "folder_id", "body_text", "body_html")):
            fail(
                "invalid_argument",
                "Update requires at least one changed field",
                write_not_started=True,
            )
        if has_body:
            body = content_html(p)
            payload["new_html"] = (
                "<div><b>"
                + html.escape(p.get("title", current["title"]))
                + "</b></div>"
                + body
            )
    result = native(operation, payload)
    return result if operation == "notes_delete" else with_revision(result)


def perform(operation, payload):
    try:
        return _perform(operation, payload)
    except Exception as error:
        from productivity_contract import ContractError

        if (
            isinstance(error, ContractError)
            and error.error["code"] == "invalid_argument"
        ):
            error.error["write_not_started"] = True
        raise
