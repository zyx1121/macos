import { z } from "zod";
import { envelopeOutput } from "../core/schema.ts";
import { scriptTool, type ToolboxTool } from "../core/tool.ts";

const id = z.string().min(1).describe("Opaque ID returned by this plugin; never use a title as an ID.");
const title = z.string().trim().min(1).max(1000);
const text = z.string().max(200000);
const revision = z.string().min(1).describe("Revision returned by get. A stale revision fails without writing.");
const key = z.string().min(1).max(200).describe("Unique request key. Reuse only to retry the same create request; prevents duplicate creation.");
const date = z.iso.date();
const moment = z.iso.datetime({ offset: true }).describe("ISO 8601 timestamp with UTC offset, e.g. 2026-10-18T23:00:00+08:00.");
export const schedule = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("date"), date }),
  z.object({ kind: z.literal("datetime"), at: moment, time_zone: z.string().min(1).describe("IANA time zone, e.g. Asia/Taipei. Must agree with the timestamp offset.") }),
]);
const nullableText = text.nullable().optional();
const url = z.url().nullable().optional();
const alarms = z.array(z.number().int().min(0).max(525600)).max(10).describe("Minutes before the start/due time. [] clears alarms. Date-only reminders require an explicit timed reminder instead.");
const recurrence = z.object({ frequency: z.enum(["daily", "weekly", "monthly", "yearly"]), interval: z.number().int().min(1).max(100).default(1), count: z.number().int().min(1).max(10000).optional(), until: moment.optional() }).refine(r => !(r.count && r.until), "Choose count or until, not both.");
const nativeRecurrence = z.array(z.object({ frequency: z.enum(["daily", "weekly", "monthly", "yearly"]), interval: z.number().int(), count: z.number().int().nullable(), until: moment.nullable(), days_of_week: z.array(z.object({ day: z.number().int(), week: z.number().int() })), days_of_month: z.array(z.number().int()), months_of_year: z.array(z.number().int()), weeks_of_year: z.array(z.number().int()), days_of_year: z.array(z.number().int()), set_positions: z.array(z.number().int()), first_day_of_week: z.number().int() })).nullable();
const scope = z.enum(["this", "future"]).describe("Required for recurring events: this occurrence, or this occurrence and future ones.");
const paging = { limit: z.number().int().min(1).max(100).default(30), cursor: z.string().optional().describe("Opaque next_cursor from the same query. A stale cursor requires restarting the query.") };
const baseItem = { id, title: z.string(), revision: z.string() };
const container = z.looseObject({ id, title: z.string(), account: z.string(), writable: z.boolean().nullable() });
const noteSummary = z.looseObject({ ...baseItem, folder_id: id, created_at: moment.nullable(), modified_at: moment.nullable(), locked: z.boolean(), shared: z.boolean(), attachment_count: z.number().int(), preview: z.string() });
const note = noteSummary.extend({ body_html: z.string(), body_text: z.string() });
const event = z.looseObject({ ...baseItem, calendar_id: id, start: schedule, end: schedule, notes: z.string().nullable(), url: z.string().nullable(), location: z.string().nullable(), alarms_minutes_before: z.array(z.number()), recurring: z.boolean(), recurrence: nativeRecurrence, occurrence_at: moment, modified_at: moment.nullable() });
const reminder = z.looseObject({ ...baseItem, list_id: id, due: schedule.nullable(), notes: z.string().nullable(), url: z.string().nullable(), completed: z.boolean(), priority: z.number().int(), alarms_minutes_before: z.array(z.number()), recurring: z.boolean(), recurrence: nativeRecurrence, modified_at: moment.nullable() });
const page = (item: z.ZodType) => z.object({ items: z.array(item), next_cursor: z.string().nullable() });
const deleted = z.object({ id, deleted: z.literal(true) });
const read = { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false };
const create = { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: false };
const update = { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: false };
function tool(name: string, description: string, inputSchema: z.ZodRawShape, output: z.ZodType, mode: "read" | "create" | "update"): ToolboxTool {
  return scriptTool({ name, description, inputSchema, outputSchema: envelopeOutput(output), annotations: mode === "read" ? read : mode === "create" ? create : update,
    script: "productivity.py", requires: name.startsWith("notes_") ? ["platform:darwin", "binary:uv", "binary:osascript"] : ["platform:darwin", "binary:uv"],
    envelope: true, timeoutMs: 90000, buildArgs: () => [name], buildStdin: input => JSON.stringify(input), truncationHint: "use get for one item or reduce limit; never update from truncated content" });
}
const matching = { query: z.string().min(1).describe("Case-insensitive substring of title or body/notes."), ...paging };
const targetEvent = { id, occurrence_at: moment.optional().describe("Occurrence timestamp returned by list/get. Required when targeting a recurring event."), scope: scope.optional() };
const writeEvent = { title, start: schedule, end: schedule, notes: nullableText, location: nullableText, url, alarms_minutes_before: alarms.optional(), recurrence: recurrence.nullable().optional() };
const writeReminder = { title, due: schedule.nullable().optional(), notes: nullableText, url, priority: z.union([z.literal(0), z.literal(1), z.literal(5), z.literal(9)]).optional(), alarms_minutes_before: alarms.optional(), recurrence: recurrence.nullable().optional() };
export const calendarTools: ToolboxTool[] = [
  tool("calendar_list_calendars", "List calendars with opaque IDs, accounts and writability. Select an explicit calendar_id before creating an event.", {}, z.array(container), "read"),
  tool("calendar_list_events", "List event occurrences overlapping a time range, including full details and revisions. Recurring occurrences have their own occurrence_at.", { calendar_id: id.optional(), from: moment, to: moment, ...paging }, page(event), "read"),
  tool("calendar_search_events", "Find events by title or notes within a time range. Returns IDs and occurrence timestamps for precise follow-up calls.", { calendar_id: id.optional(), from: moment, to: moment, ...matching }, page(event), "read"),
  tool("calendar_get_event", "Read one event and its current revision. For recurring events, pass the occurrence_at returned by list/search.", { id, occurrence_at: moment.optional() }, event, "read"),
  tool("calendar_create_event", "Create an event in an explicit calendar with a retry key. Date-only end is exclusive. Zoned timestamps must match time_zone.", { calendar_id: id, request_key: key, ...writeEvent }, event, "create"),
  tool("calendar_update_event", "Patch an event by ID and expected_revision. Omitted fields stay unchanged; null clears nullable fields. Recurring events require occurrence_at and scope.", { ...targetEvent, expected_revision: revision, calendar_id: id.optional(), ...Object.fromEntries(Object.entries(writeEvent).map(([k,v]) => [k,v.optional()])), confirm: z.literal(true) }, event, "update"),
  tool("calendar_delete_event", "Delete an event by ID and expected_revision. Recurring events require occurrence_at and scope; never selects by title.", { ...targetEvent, expected_revision: revision, confirm: z.literal(true) }, deleted, "update"),
];
export const remindersTools: ToolboxTool[] = [
  tool("reminders_list_lists", "List reminder lists with opaque IDs, accounts and writability. Select an explicit list_id before creating a reminder.", {}, z.array(container), "read"),
  tool("reminders_list", "List reminders across all lists or one list. Filter completion and due dates; undated reminders are included only without a date filter.", { list_id: id.optional(), completed: z.boolean().optional(), due_from: date.optional(), due_to: date.optional(), ...paging }, page(reminder), "read"),
  tool("reminders_search", "Find reminders by title or notes across lists, with full details and revisions. Completion and due-date filters are optional.", { list_id: id.optional(), completed: z.boolean().optional(), due_from: date.optional(), due_to: date.optional(), ...matching }, page(reminder), "read"),
  tool("reminders_get", "Read a reminder by opaque ID, including notes, due time, alarms and current revision.", { id }, reminder, "read"),
  tool("reminders_create", "Create a reminder with an explicit list and retry key. A date-only due has no time; use a zoned datetime for timed alarms.", { list_id: id, request_key: key, ...writeReminder }, reminder, "create"),
  tool("reminders_update", "Patch a reminder by ID and expected_revision. Omitted fields stay unchanged; null clears nullable fields. completed can also reopen a task.", { id, expected_revision: revision, list_id: id.optional(), ...Object.fromEntries(Object.entries(writeReminder).map(([k,v]) => [k,v.optional()])), completed: z.boolean().optional(), confirm: z.literal(true) }, reminder, "update"),
  tool("reminders_complete", "Complete a reminder by ID and expected_revision. Already completed reminders succeed unchanged. Recurring reminders follow Apple's next-occurrence behavior.", { id, expected_revision: revision, confirm: z.literal(true) }, reminder, "update"),
  tool("reminders_delete", "Delete a reminder by ID and expected_revision. For a recurring reminder this deletes the task and its recurrence.", { id, expected_revision: revision, confirm: z.literal(true) }, deleted, "update"),
];
export const notesTools: ToolboxTool[] = [
  tool("notes_list_folders", "List Notes folders with opaque IDs, account names and writability. Includes nested folders; select a folder_id for new notes.", {}, z.array(container), "read"),
  tool("notes_list", "List note metadata and previews without reading full bodies into context. Locked notes are discoverable but their contents remain inaccessible.", { folder_id: id.optional(), ...paging }, page(noteSummary), "read"),
  tool("notes_search", "Search unlocked notes by title or plain text. Returns IDs, previews and revisions; use notes_get before editing.", { folder_id: id.optional(), ...matching }, page(noteSummary), "read"),
  tool("notes_get", "Read a note's HTML, plain text and revision by ID. Locked notes return locked. Large bodies may be truncated; never overwrite from truncated content.", { id }, note, "read"),
  tool("notes_create", "Create a note in an explicit folder with a retry key. body_text is escaped into HTML; pass body_html instead to preserve intentional formatting.", { folder_id: id, request_key: key, title, body_text: text.optional(), body_html: text.optional() }, note, "create"),
  tool("notes_update", "Patch note title/body/folder by ID and revision. Body replacement on notes with attachments is refused; title/folder changes preserve attachments.", { id, expected_revision: revision, title: title.optional(), folder_id: id.optional(), body_text: text.optional(), body_html: text.optional(), confirm: z.literal(true) }, note, "update"),
  tool("notes_append", "Append escaped text or HTML to an unlocked note by ID and revision. Attachment-bearing notes are refused to avoid destructive HTML round-trips.", { id, expected_revision: revision, body_text: text.optional(), body_html: text.optional(), confirm: z.literal(true) }, note, "update"),
  tool("notes_delete", "Delete a note by ID and expected_revision. The native Notes app controls Recently Deleted behavior.", { id, expected_revision: revision, confirm: z.literal(true) }, deleted, "update"),
];
