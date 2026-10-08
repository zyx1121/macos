import { test, expect, beforeEach } from "bun:test";
import { z } from "zod";
import { allTools } from "../src/tools/index.ts";
import { selectRunnableTools } from "../src/core/tool.ts";
import { clearRequirementCache } from "../src/core/requires.ts";
beforeEach(clearRequirementCache);
test("tools register only when their host dependencies are present", async () => {
  const mac = await selectRunnableTools(allTools, { check: async r => ["platform:darwin", "binary:uv", "binary:osascript", "binary:screencapture"].includes(r) });
  expect(mac.registered).toHaveLength(64);
  clearRequirementCache();
  const linux = await selectRunnableTools(allTools, { check: async r => ["platform:linux", "binary:uv"].includes(r) });
  expect(linux.registered.map(t=>t.name)).toEqual(["macos_get_capabilities"]);

});
test("missing dependencies hide tools without crashing", async () => {
  const selected = await selectRunnableTools(allTools, { check: async () => { throw Error("missing"); } });
  expect(selected.registered.map(t=>t.name)).toEqual(["macos_get_capabilities"]);
  expect(selected.hidden).toHaveLength(63);
});
test("tool contracts preserve confirmations and read/write annotations", () => {
  expect(new Set(allTools.map(t => t.name)).size).toBe(64);
  for (const tool of allTools) {
    expect(Object.keys(tool.outputSchema).length).toBeGreaterThan(0);
    expect(typeof tool.annotations.readOnlyHint).toBe("boolean");
    expect(tool.description.length).toBeLessThanOrEqual(300);
    if (tool.annotations.destructiveHint) {
      const confirm = tool.inputSchema.confirm as z.ZodType;
      expect(confirm.safeParse(true).success).toBe(true);
      expect(confirm.safeParse(false).success).toBe(false);
      expect(confirm.safeParse(undefined).success).toBe(false);
    }
  }
});
