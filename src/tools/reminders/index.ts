import { z } from "zod";
import { pushFlag, pushPos } from "../../core/argv.ts";
import { envelopeOutput } from "../../core/schema.ts";
import { scriptTool, type ToolboxTool } from "../../core/tool.ts";

const script = "reminders.py";
/** Reads go through EventKit (Reminders.app stays closed), writes through AppleScript: macOS only, and the script itself runs under uv. */
const requires = ["platform:darwin", "binary:osascript", "binary:uv"];
const envelope = true;
const timeoutMs = 60000;

const read = { readOnlyHint: true, openWorldHint: false } as const;
const write = { readOnlyHint: false, destructiveHint: false, openWorldHint: false } as const;
const destroy = { readOnlyHint: false, destructiveHint: true, openWorldHint: false } as const;

export const remindersTools: ToolboxTool[] = [
  scriptTool({
    name: "reminders_list_lists",
    description: "List Reminders.app lists. Use before add/list/complete/delete when the target list name is unknown.",
    inputSchema: {},
    outputSchema: envelopeOutput(z.array(z.looseObject({ name: z.string() }))),
    annotations: read,
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: () => ["show-lists"],
  }),
  scriptTool({
    name: "reminders_list",
    description: "List reminders in a list.",
    inputSchema: { list_name: z.string().optional().describe("Reminder list name."), show_done: z.boolean().optional().describe("Include completed reminders."), limit: z.number().optional().describe("Maximum reminders.") },
    annotations: read,
    script,
    requires,
    envelope,
    timeoutMs,
    truncationHint: "set limit, or leave show_done off",
    buildArgs: (input) => {
      const argv = ["list"];
      pushFlag(argv, "--list", input.list_name);
      pushFlag(argv, "--show-done", input.show_done);
      pushFlag(argv, "--limit", input.limit);
      return argv;
    },
  }),
  scriptTool({
    name: "reminders_add",
    description: "Add a reminder. Writes to the user's real Reminders.app and syncs to their other devices.",
    inputSchema: { name: z.string().describe("Reminder text."), due: z.string().optional().describe("Due time/date."), list_name: z.string().optional().describe("Target list."), notes: z.string().optional().describe("Reminder notes.") },
    annotations: write,
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["add"];
      pushPos(argv, input.name);
      pushFlag(argv, "--due", input.due);
      pushFlag(argv, "--list", input.list_name);
      pushFlag(argv, "--notes", input.notes);
      return argv;
    },
  }),
  scriptTool({
    name: "reminders_complete",
    description: "Mark the first exact-matching reminder as completed. Only the first match is touched; completing an already-completed reminder is a no-op.",
    inputSchema: { name: z.string().describe("Exact reminder name."), list_name: z.string().optional().describe("List to search."), confirm: z.literal(true).describe("Required explicit confirmation.") },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: false },
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["done"];
      pushPos(argv, input.name);
      pushFlag(argv, "--list", input.list_name);
      return argv;
    },
  }),
  scriptTool({
    name: "reminders_delete",
    description: "Delete the first exact-matching reminder. Destructive and irreversible; confirm the exact name with reminders_list first, since only the first match is removed.",
    inputSchema: { name: z.string().describe("Exact reminder name."), list_name: z.string().optional().describe("List to search."), confirm: z.literal(true).describe("Required explicit confirmation.") },
    annotations: destroy,
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["delete"];
      pushPos(argv, input.name);
      pushFlag(argv, "--list", input.list_name);
      return argv;
    },
  }),
];
