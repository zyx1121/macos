import { z } from "zod";
import { tool, container, event } from "./productivity.ts";
const id=z.string().min(1);
const title=z.string().trim().min(1).max(1000);
const request_key=z.string().min(1).max(200);
const expected_revision=z.string().min(1);
const confirm=z.literal(true);
const target={id,expected_revision,confirm};
const source=z.looseObject({id,title:z.string()});
const managed=container.extend({revision:z.string()});
const deleted=z.object({id,deleted:z.literal(true)});
export const organizationTools=[
 tool("notes_list_accounts","List Notes accounts and opaque IDs before creating a root folder.",{},z.array(source),"read"),
 tool("notes_get_folder","Read a folder's identity, parent, content counts and revision before modifying it.",{id},managed,"read"),
 tool("notes_create_folder","Create a Notes folder under an explicit account or parent folder. Nested folders must belong to the same account.",{account_id:id,parent_id:id.optional(),title,request_key},managed,"create"),
 tool("notes_update_folder","Rename or move a folder within its account. Refuses cycles and uses the current revision; omitted fields stay unchanged.",{...target,title:title.optional(),parent_id:id.optional()},managed,"update"),
 tool("notes_delete_folder","Delete only an empty root Notes folder with no notes or child folders. Nested-folder deletion is refused because native Apple Events does not reliably perform it.",target,deleted,"update"),
 ...(["calendar","reminders"] as const).flatMap(f=>{
  const object=f==="calendar"?"calendar":"list";
  return [
   tool(`${f}_list_sources`,"List native account/source IDs for creating calendars or reminder lists. Source permissions are checked by the native store.",{},z.array(source),"read"),
   tool(`${f}_get_${object}`,"Read a calendar/list by ID, including content count and revision.",{id},managed,"read"),
   tool(`${f}_create_${object}`,"Create a calendar/list in an explicit native source with a durable retry key.",{source_id:id,title,request_key},managed,"create"),
   tool(`${f}_update_${object}`,"Rename a calendar/list by ID and current revision. Account migration is not supported.",{...target,title},managed,"update"),
   tool(`${f}_delete_${object}`,"Delete only an empty calendar/list by ID and current revision. Refuses any remaining native item.",target,deleted,"update"),
  ];
 }),
];
const moment=z.iso.datetime({offset:true});
const policy={calendar_ids:z.array(id).min(1).describe("Explicit calendars to inspect; never assumes unqueried calendars are free."),from:moment,to:moment,time_zone:z.string().min(1),include_all_day:z.boolean().default(true),include_free_events:z.boolean().default(false),exclude_event_ids:z.array(id).default([])};
const coverage={from:moment,to:moment,calendar_ids:z.array(id),policy:z.looseObject({time_zone:z.string(),include_all_day:z.boolean(),include_free_events:z.boolean(),exclude_event_ids:z.array(id)}),coverage:z.literal("local_synced_events_only")};
export const planningTools=[
 tool("calendar_check_conflicts","Find overlapping occurrences in explicit calendars. Half-open intervals allow adjacent events; canceled/free events follow the declared policy.",policy,z.object({...coverage,conflicts:z.array(event),has_conflicts:z.boolean()}),"read"),
 tool("calendar_find_free_slots","Return maximal free intervals long enough for a task, within explicit calendars/range and optional local working hours. Includes coverage and policy.",{...policy,duration_minutes:z.number().int().min(1).max(10080),working_hours:z.object({start:z.string().regex(/^\d{2}:\d{2}$/),end:z.string().regex(/^\d{2}:\d{2}$/),weekdays:z.array(z.number().int().min(1).max(7)).min(1).max(7)}).optional(),limit:z.number().int().min(1).max(100).default(30)},z.object({...coverage,slots:z.array(z.object({start:moment,end:moment,duration_minutes:z.number()})),has_more:z.boolean(),minimum_duration_minutes:z.number()}),"read"),
];
