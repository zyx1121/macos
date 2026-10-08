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
  function walk(f,account,parent) {
    const id=f.id(); if(seen[id]) return; seen[id]=true;
    result.push({object:f,id:id,title:f.name(),account:account,parent_id:parent,shared:f.shared(),writable:null});
    f.folders().forEach(x=>walk(x,account,id));
  }
  app.accounts().forEach(a=>a.folders().forEach(f=>walk(f,a.name(),null)));
  return result;
}
function folder(id) { const f=folderObjects().find(f=>f.id===id); if(!f) error('not_found','Notes folder ID no longer exists'); return f.object; }
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
  if(operation==='notes_list_folders') {
    result=folderObjects().map(f=>({id:f.id,title:f.title,account:f.account,parent_id:f.parent_id,shared:f.shared,writable:f.writable}));
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
