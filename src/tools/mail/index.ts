import { z } from "zod";
import { scriptTool } from "../../core/tool.ts";
import { envelopeOutput } from "../../core/schema.ts";
const id=z.string().min(1);
const moment=z.iso.datetime({offset:true});
const paging={limit:z.number().int().min(1).max(100).default(30),cursor:z.string().optional()};
const account=z.looseObject({id,name:z.string(),addresses:z.array(z.string())});
const mailbox=z.looseObject({id,title:z.string(),account_id:id.nullable(),parent_id:id.nullable()});
const summary=z.looseObject({id,mailbox_id:id,subject:z.string(),sender:z.string(),received_at:moment.nullable(),read:z.boolean()});
const message=summary.extend({body_text:z.string(),to:z.array(z.string()),cc:z.array(z.string()),bcc:z.array(z.string()),attachment_count:z.number().int(),revision:z.string()});
const draft=z.looseObject({id,subject:z.string(),body_text:z.string(),sender:z.string(),to:z.array(z.string()),cc:z.array(z.string()),bcc:z.array(z.string()),visible:z.boolean(),revision:z.string()});
const page=(item:z.ZodType)=>z.object({items:z.array(item),next_cursor:z.string().nullable()});
const fields={subject:z.string().max(1000),body_text:z.string().max(200000),to:z.array(z.email()).max(100),cc:z.array(z.email()).max(100).optional(),bcc:z.array(z.email()).max(100).optional(),account_id:id.optional(),visible:z.boolean().optional()};
const filter={account_id:id.optional(),mailbox_id:id.optional(),received_from:moment.optional(),received_to:moment.optional(),unread:z.boolean().optional(),...paging};
function tool(name:string,description:string,inputSchema:z.ZodRawShape,output:z.ZodType,mode:"read"|"create"|"update") {
 return scriptTool({name,description,inputSchema,outputSchema:envelopeOutput(output),annotations:{readOnlyHint:mode==="read",destructiveHint:mode==="update",idempotentHint:mode!=="update",openWorldHint:false},requires:["platform:darwin","binary:uv","binary:osascript"],script:"productivity.py",envelope:true,timeoutMs:130000,buildArgs:()=>[name],buildStdin:input=>JSON.stringify(input),truncationHint:"reduce limit or get one message; never overwrite a truncated draft"});
}
export const mailTools=[
 tool("mail_list_accounts","List Mail accounts with opaque IDs and sender addresses.",{},z.array(account),"read"),
 tool("mail_list_mailboxes","Discover mailbox IDs and account/parent relationships, including nested mailboxes. IDs change when a mailbox is renamed or moved.",{account_id:id.optional()},z.array(mailbox),"read"),
 tool("mail_list_messages","List synced message summaries by explicit mailbox or account; omitted mailbox spans all discovered mailboxes. Date bounds are [from,to).",filter,page(summary),"read"),
 tool("mail_search_messages","Search subject and sender across synced mailboxes with account, mailbox, unread and date filters. Returns IDs; never selects the first matching subject.",{...filter,query:z.string().min(1)},page(summary),"read"),
 tool("mail_get_message","Read one synced message by opaque ID, including text, recipients, attachments count and revision. Renamed/moved mailboxes require rediscovery.",{id},message,"read"),
 tool("mail_list_drafts","List open native compose drafts and revisions. Closed/reopened drafts receive new IDs. Discarded compose objects are filtered from the native cache.",paging,page(draft),"read"),
 tool("mail_create_draft","Create and save a Mail compose draft with a retry key. Sender can be selected by account ID. visible defaults true. Returns an ID and never sends.",{...fields,request_key:z.string().min(1).max(200)},draft,"create"),
 tool("mail_get_draft","Read an open compose draft by native ID before editing. If closed or reopened, rediscover via mail_list_drafts.",{id},draft,"read"),
 tool("mail_update_draft","Patch a compose draft by ID/revision. Body replacement rebuilds a plain draft and returns a new ID, preserving omitted fields. Attachment/reply/forward body edits are refused. Never sends.",{id,expected_revision:z.string().min(1),confirm:z.literal(true),...Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,v.optional()]))},draft,"update"),
 tool("mail_delete_draft","Discard an open compose draft by ID and revision, including its saved draft copy. Never deletes received mail or sends a message.",{id,expected_revision:z.string().min(1),confirm:z.literal(true)},z.object({id,deleted:z.literal(true)}),"update"),
];
