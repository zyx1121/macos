import { z } from "zod";
import { pushPos } from "../../core/argv.ts";
import { scriptTool, type ToolboxTool } from "../../core/tool.ts";

const script = "screenshot.sh";
/** screenshot.sh wraps screencapture(1); a bash script, so no uv. */
const requires = ["platform:darwin", "binary:screencapture"];
const envelope = false;
const timeoutMs = 60000;
const out = z.string().optional().describe("Output PNG path. Default: /tmp/screenshot.png.");

/** Writes an image file; captures whatever is on the user's screen. */
const capture = { readOnlyHint: false, destructiveHint: false, openWorldHint: false } as const;
const blocksOnHuman = "Blocks waiting for the user to drag or click, so never call it unattended, in a loop, or while they are away.";

export const screenshotTools: ToolboxTool[] = [
  scriptTool({
    name: "screenshot_full",
    description: "Capture the full macOS screen to a PNG file. Unattended, but it records whatever is on screen, including anything private in view.",
    inputSchema: { out },
    annotations: capture,
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv: string[] = [];
      pushPos(argv, input.out);
      return argv;
    },
  }),
  scriptTool({
    name: "screenshot_area",
    description: `Interactively capture a dragged screen region. ${blocksOnHuman}`,
    inputSchema: { out },
    annotations: capture,
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["--area"];
      pushPos(argv, input.out);
      return argv;
    },
  }),
  scriptTool({
    name: "screenshot_window",
    description: `Interactively capture a clicked window. ${blocksOnHuman}`,
    inputSchema: { out },
    annotations: capture,
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["--window"];
      pushPos(argv, input.out);
      return argv;
    },
  }),
  scriptTool({
    name: "screenshot_region",
    description: "Capture a known pixel region with no UI interaction. Prefer this over screenshot_area when the coordinates are already known.",
    inputSchema: { region: z.string().describe("x,y,w,h."), out },
    annotations: capture,
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: (input) => {
      const argv = ["--region", input.region];
      pushPos(argv, input.out);
      return argv;
    },
  }),
  scriptTool({
    name: "screenshot_clipboard",
    description: "Capture full screen to the clipboard. No file path is produced, so the image cannot be read back here; it also overwrites whatever the user had copied.",
    inputSchema: {},
    annotations: capture,
    script,
    requires,
    envelope,
    timeoutMs,
    buildArgs: () => ["--clipboard"],
  }),
];
