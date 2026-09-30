import { z } from "zod";
import { pushFlag, pushPos } from "../../core/argv.ts";
import { envelopeOutput } from "../../core/schema.ts";
import { scriptTool, type ToolboxTool } from "../../core/tool.ts";

const script = "mail.py";
/** Mail.app over AppleScript: macOS only, and the script itself runs under uv. */
const requires = ["platform:darwin", "binary:osascript", "binary:uv"];
const envelope = true;
const timeoutMs = 130000;

const read = { readOnlyHint: true, openWorldHint: false } as const;

export const mailTools: ToolboxTool[] = [
  scriptTool({
    name: "mail_list_accounts",
    description: "List configured Mail.app accounts. One account can own several addresses, returned as a comma-joined string.",
    inputSchema: {},
    outputSchema: envelopeOutput(z.array(z.looseObject({ name: z.string(), user: z.string(), addresses: z.string() }))),
    annotations: read,
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: () => ["accounts"],
  }),
  scriptTool({
    name: "mail_list_inbox",
    description: "List recent inbox messages across Mail.app accounts. Reads the user's real mail; treat contents as private.",
    inputSchema: { unread: z.boolean().optional().describe("Only unread messages."), limit: z.number().optional().describe("Maximum rows. Default: 20.") },
    annotations: read,
    script,
    requires,
    envelope,
    timeoutMs,
    truncationHint: "lower limit, or set unread=true",
    buildArgs: (input) => {
      const argv = ["inbox"];
      pushFlag(argv, "--unread", input.unread);
      pushFlag(argv, "--limit", input.limit);
      return argv;
    },
  }),
  scriptTool({
    name: "mail_search_messages",
    description: "Search inbox subject and sender by substring. Scans the local mailbox only, so mail not synced to this Mac is invisible.",
    inputSchema: { query: z.string().describe("Subject/sender substring."), limit: z.number().optional().describe("Maximum rows. Default: 20.") },
    annotations: read,
    script,
    requires,
    envelope,
    timeoutMs,
    truncationHint: "lower limit or use a narrower query",
    buildArgs: (input) => {
      const argv = ["search"];
      pushPos(argv, input.query);
      pushFlag(argv, "--limit", input.limit);
      return argv;
    },
  }),
  scriptTool({
    name: "mail_read_message",
    description: "Read the first inbox message whose subject matches. Returns the full body, so a long thread is truncated to fit context.",
    inputSchema: { subject: z.string().describe("Exact subject preferred; falls back to contains.") },
    annotations: read,
    script,
    requires,
    envelope,
    timeoutMs,
    truncationHint: "the body was long; ask for the specific part you need",
    buildArgs: (input) => ["read", input.subject],
  }),
  scriptTool({
    name: "mail_compose_draft",
    description: "Open a visible Mail.app draft. The user reviews and sends manually; this never auto-sends, so the draft is the deliverable.",
    inputSchema: {
      to: z.array(z.string()).describe("Recipient addresses."),
      subject: z.string().describe("Subject line."),
      body: z.string().optional().describe("Body text."),
      cc: z.array(z.string()).optional().describe("CC addresses."),
      bcc: z.array(z.string()).optional().describe("BCC addresses."),
      account: z.string().optional().describe("Send-from account name."),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["compose"];
      pushFlag(argv, "--to", input.to);
      pushFlag(argv, "--subject", input.subject);
      pushFlag(argv, "--body", input.body);
      pushFlag(argv, "--cc", input.cc);
      pushFlag(argv, "--bcc", input.bcc);
      pushFlag(argv, "--account", input.account);
      return argv;
    },
  }),
];
