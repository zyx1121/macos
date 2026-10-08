import { expect, test } from "bun:test";
import { z } from "zod";
import { calendarTools, remindersTools, notesTools, schedule } from "../src/tools/productivity.ts";
const tools = [...calendarTools, ...remindersTools, ...notesTools];
const input = (name:string) => z.object(tools.find(t=>t.name===name)!.inputSchema);
test("old selectors and entry points are removed", () => {
  expect(tools.some(t => /_add/.test(t.name))).toBe(false);
  expect(input("calendar_delete_event").safeParse({summary:"same",cal:"Home",confirm:true}).success).toBe(false);
  expect(input("reminders_complete").safeParse({name:"same",confirm:true}).success).toBe(false);
});
test("create has explicit destination and retry key", () => {
  const base={title:"Deadline", start:{kind:"date",date:"2026-10-18"},end:{kind:"date",date:"2026-10-19"}};
  expect(input("calendar_create_event").safeParse(base).success).toBe(false);
  expect(input("calendar_create_event").safeParse({...base,calendar_id:"c",request_key:"k"}).success).toBe(true);
});
test("timestamps require offsets and a zone", () => {
  expect(schedule.safeParse({kind:"datetime",at:"2026-10-18T23:00:00",time_zone:"Asia/Taipei"}).success).toBe(false);
  expect(schedule.safeParse({kind:"datetime",at:"2026-10-18T23:00:00+08:00",time_zone:"Asia/Taipei"}).success).toBe(true);
});
test("updates require revisions and confirmations", () => {
  for(const tool of tools.filter(t=>t.annotations.destructiveHint)) {
    const parsed=z.object(tool.inputSchema);
    expect(parsed.safeParse({id:"x",confirm:true}).success).toBe(false);
    expect(parsed.safeParse({id:"x",expected_revision:"r"}).success).toBe(false);
  }
});
test("all productivity outputs reject unstructured data", () => {
  for(const tool of tools) expect(z.object(tool.outputSchema).safeParse({data:{arbitrary:true}}).success).toBe(false);
});

test("sanitized native macOS responses satisfy published item schemas", async () => {
  const fixtures = await Bun.file(new URL("./native-fixtures.json", import.meta.url)).json();
  for (const [name,data] of Object.entries(fixtures)) {
    const tool=tools.find(t=>t.name===name)!;
    const parsed=z.object(tool.outputSchema).safeParse({data,metadata:{schema_version:"v2"}});
    expect(parsed.success ? null : parsed.error.issues).toBeNull();
  }
});
