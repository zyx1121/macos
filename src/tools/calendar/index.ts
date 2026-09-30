import { z } from "zod";
import { pushFlag, pushPos } from "../../core/argv.ts";
import { envelopeOutput } from "../../core/schema.ts";
import { scriptTool, type ToolboxTool } from "../../core/tool.ts";

const envelope = true;
const timeoutMs = 70000;
const script = "calendar.py";
/** Reads go through EventKit (Calendar.app stays closed), writes through AppleScript: macOS only, and the script itself runs under uv. */
const requires = ["platform:darwin", "binary:osascript", "binary:uv"];

const read = { readOnlyHint: true, openWorldHint: false } as const;
const write = { readOnlyHint: false, destructiveHint: false, openWorldHint: false } as const;
const destroy = { readOnlyHint: false, destructiveHint: true, openWorldHint: false } as const;

export const calendarTools: ToolboxTool[] = [
  scriptTool({
    name: "calendar_list_calendars",
    description: "List Calendar.app calendars with writability. Use before add/list/search/delete when the target calendar name is unknown. Several calendars can share a display name, so prefer an exact string the user confirmed.",
    inputSchema: {},
    outputSchema: envelopeOutput(z.array(z.looseObject({ name: z.string(), writable: z.boolean() }))),
    annotations: read,
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: () => ["show-cals"],
  }),
  scriptTool({
    name: "calendar_list_events",
    description: "List Calendar.app events across one or all calendars within a date range. Defaults to today through seven days ahead.",
    inputSchema: {
      cal: z.string().optional().describe("Calendar name filter. Default: all calendars."),
      start: z.string().optional().describe("Range start. Accepts YYYY-MM-DD, YYYY-MM-DDTHH:MM, today, tomorrow, now, or next week."),
      end: z.string().optional().describe("Range end. Same formats as start. Default: start + 7 days."),
      limit: z.number().optional().describe("Maximum events returned."),
    },
    annotations: read,
    script,
    requires,
    envelope,
    timeoutMs,
    truncationHint: "narrow the date range or set limit",
    buildArgs: (input) => {
      const argv = ["list"];
      pushFlag(argv, "--cal", input.cal);
      pushFlag(argv, "--from", input.start);
      pushFlag(argv, "--to", input.end);
      pushFlag(argv, "--limit", input.limit);
      return argv;
    },
  }),
  scriptTool({
    name: "calendar_add_event",
    description: "Add a Calendar.app event. Writes to the user's real calendar and syncs to their other devices; there is no undo beyond calendar_delete_event.",
    inputSchema: {
      summary: z.string().describe("Event title."),
      at: z.string().describe("Start time: YYYY-MM-DDTHH:MM, tomorrow, etc."),
      duration: z.number().optional().describe("Duration in minutes. Default: 60."),
      cal: z.string().optional().describe("Target calendar. Default: first writable calendar."),
      location: z.string().optional().describe("Event location."),
      notes: z.string().optional().describe("Event notes."),
    },
    annotations: write,
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["add"];
      pushPos(argv, input.summary);
      pushFlag(argv, "--at", input.at);
      pushFlag(argv, "--duration", input.duration);
      pushFlag(argv, "--cal", input.cal);
      pushFlag(argv, "--location", input.location);
      pushFlag(argv, "--notes", input.notes);
      return argv;
    },
  }),
  scriptTool({
    name: "calendar_search_events",
    description: "Search Calendar.app event summaries within a date range. Defaults to today through 30 days ahead.",
    inputSchema: {
      query: z.string().describe("Case-insensitive substring to match against event summaries."),
      cal: z.string().optional().describe("Calendar name filter. Default: all calendars."),
      start: z.string().optional().describe("Range start. Default: today."),
      end: z.string().optional().describe("Range end. Default: today + 30 days."),
      limit: z.number().optional().describe("Maximum events returned."),
    },
    annotations: read,
    script,
    requires,
    envelope,
    timeoutMs,
    truncationHint: "narrow the date range or set limit",
    buildArgs: (input) => {
      const argv = ["search"];
      pushPos(argv, input.query);
      pushFlag(argv, "--cal", input.cal);
      pushFlag(argv, "--from", input.start);
      pushFlag(argv, "--to", input.end);
      pushFlag(argv, "--limit", input.limit);
      return argv;
    },
  }),
  scriptTool({
    name: "calendar_delete_event",
    description: "Delete the first event with an exact matching summary in one explicit calendar. Destructive and irreversible; confirm the exact event with calendar_search_events first, since only the first match is removed.",
    inputSchema: {
      summary: z.string().describe("Exact event summary."),
      cal: z.string().describe("Calendar to search. Required; no cross-calendar fuzzy delete."),
      start: z.string().optional().describe("Range start. Default: today."),
      end: z.string().optional().describe("Range end. Default: today + 30 days."),
      confirm: z.literal(true).describe("Required explicit confirmation."),
    },
    annotations: destroy,
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["delete"];
      pushPos(argv, input.summary);
      pushFlag(argv, "--cal", input.cal);
      pushFlag(argv, "--from", input.start);
      pushFlag(argv, "--to", input.end);
      return argv;
    },
  }),
];
