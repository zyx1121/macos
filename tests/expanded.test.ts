import { test, expect } from "bun:test";
import { z } from "zod";
import { allTools } from "../src/tools/index.ts";
import { recurrence } from "../src/tools/productivity.ts";
const input=(name:string)=>z.object(allTools.find(t=>t.name===name)!.inputSchema).strict();
test("container creation requires opaque source/account and a retry key",()=>{
 for(const [name,source] of [["notes_create_folder","account_id"],["calendar_create_calendar","source_id"],["reminders_create_list","source_id"]]){
  expect(input(name!).safeParse({title:"Course"}).success).toBe(false);
  expect(input(name!).safeParse({title:"Course",[source!]:"source-id",request_key:"create-course"}).success).toBe(true);
 }
});
test("complex recurrence selector ranges reject impossible ordinals",()=>{
 expect(recurrence.safeParse({frequency:"weekly",days_of_week:[{day:3},{day:5}]}).success).toBe(true);
 expect(recurrence.safeParse({frequency:"monthly",days_of_week:[{day:6}],set_positions:[-1]}).success).toBe(true);
 expect(recurrence.safeParse({frequency:"monthly",days_of_month:[0]}).success).toBe(false);
 expect(recurrence.safeParse({frequency:"weekly",days_of_week:[{day:8}]}).success).toBe(false);
});
test("planning requires explicit coverage and bounded durations",()=>{
 const base={from:"2026-10-09T09:00:00Z",to:"2026-10-09T18:00:00Z",time_zone:"UTC",duration_minutes:120};
 expect(input("calendar_find_free_slots").safeParse(base).success).toBe(false);
 expect(input("calendar_find_free_slots").safeParse({...base,calendar_ids:["calendar-id"]}).success).toBe(true);
 expect(input("calendar_find_free_slots").safeParse({...base,calendar_ids:["calendar-id"],duration_minutes:0}).success).toBe(false);
});
test("Mail selects exact IDs and removes legacy aliases",()=>{
 for(const name of ["mail_list_inbox","mail_read_message","mail_compose_draft"])expect(allTools.some(t=>t.name===name)).toBe(false);
 expect(input("mail_get_message").safeParse({subject:"Duplicate subject"}).success).toBe(false);
 expect(input("mail_get_message").safeParse({id:"opaque-message-id"}).success).toBe(true);
 expect(input("mail_update_draft").safeParse({id:"draft-id",subject:"new",confirm:true}).success).toBe(false);
});
test("draft creation validates recipients and retry key",()=>{
 const base={subject:"Coursework",body_text:"Please review",to:["recipient@example.test"],request_key:"draft-key"};
 expect(input("mail_create_draft").safeParse(base).success).toBe(true);
 expect(input("mail_create_draft").safeParse({...base,to:["not-an-address"]}).success).toBe(false);
});
test("capability discovery survives missing native dependencies",async()=>{
 const tool=allTools.find(t=>t.name==="macos_get_capabilities")!;
 const result=await tool.run({});
 expect(z.object(tool.outputSchema).safeParse(result.structuredContent).success).toBe(true);
 const content=result.structuredContent as {data:{tools:{name:string;available:boolean;missing:string[]}[]}};
 expect(content.data.tools).toHaveLength(64);
 if(process.platform!=="darwin"){
  expect(content.data.tools.find(t=>t.name==="calendar_create_event")!.available).toBe(false);
  expect(content.data.tools.find(t=>t.name==="macos_get_capabilities")!.available).toBe(true);
 }
});
