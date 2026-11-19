import { z } from "zod";
import { envelopeOutput } from "../../core/schema.ts";
import { scriptTool, type ToolboxTool } from "../../core/tool.ts";

const script = "safari.py";
/** Safari.app over AppleScript: macOS only, and the script itself runs under uv. */
const requires = ["platform:darwin", "binary:osascript", "binary:uv"];
const envelope = true;
const timeoutMs = 60000;

const read = { readOnlyHint: true, openWorldHint: false } as const;
const write = { readOnlyHint: false, destructiveHint: false, openWorldHint: true } as const;

/** Every safari tool drives the user's own live browser, not a headless one. */
const liveBrowser = "Acts on Loki's live Safari front tab, so it competes with whatever they are actually reading; for scanning pages use headless tooling instead.";
const needsAppleEvents = "Needs Safari's Develop > Allow JavaScript from Apple Events; without it the failure is an opaque osascript error.";

export const safariTools: ToolboxTool[] = [
  scriptTool({
    name: "safari_get_url",
    description: `Get Safari front tab URL. ${liveBrowser}`,
    inputSchema: {},
    outputSchema: envelopeOutput(z.looseObject({ url: z.string() })),
    annotations: read,
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: () => ["url"],
  }),
  scriptTool({
    name: "safari_get_title",
    description: `Get Safari front tab title. ${liveBrowser}`,
    inputSchema: {},
    outputSchema: envelopeOutput(z.looseObject({ title: z.string() })),
    annotations: read,
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: () => ["title"],
  }),
  scriptTool({
    name: "safari_get_text",
    description: `Get visible rendered text from Safari front tab. ${liveBrowser} Long pages are truncated.`,
    inputSchema: {},
    annotations: read,
    script,
    requires,
    envelope,
    timeoutMs,
    truncationHint: "read the page in sections, or fetch the URL directly instead of through the browser",
    buildArgs: () => ["text"],
  }),
  scriptTool({
    name: "safari_list_tabs",
    description: `List all Safari tabs across windows. Reads the user's open tabs, which may include private context.`,
    inputSchema: {},
    outputSchema: envelopeOutput(z.array(z.looseObject({ wt: z.string(), title: z.string(), url: z.string() }))),
    annotations: read,
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: () => ["tabs"],
  }),
  scriptTool({
    name: "safari_open_url",
    description: "Open a URL in the agent tab: reuses the tab this tool opened, else adds one tab to the front window (a window only when Safari has none) and focuses it. Does not wait for load. Call safari_close_tab when done.",
    inputSchema: { target: z.string().describe("URL to open.") },
    annotations: write,
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: (input) => ["open", input.target],
  }),
  scriptTool({
    name: "safari_close_tab",
    description: "Close the agent tab that safari_open_url opened. Never closes the user's own tabs; reports closed=false when no agent tab is left. Call it when done with Safari.",
    inputSchema: {},
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: false },
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: () => ["close"],
  }),
  scriptTool({
    name: "safari_get_selection",
    description: `Get current text selection in Safari front tab. ${needsAppleEvents}`,
    inputSchema: {},
    annotations: read,
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: () => ["selection"],
  }),
  scriptTool({
    name: "safari_eval_js",
    description: `Evaluate JavaScript in Safari front tab. ${needsAppleEvents} ${liveBrowser}`,
    inputSchema: { expression: z.string().describe("JavaScript expression.") },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    script,
    requires,
    envelope,
    timeoutMs,
    truncationHint: "return a narrower value from the expression instead of a whole document",
    buildArgs: (input) => ["js", input.expression],
  }),
];
