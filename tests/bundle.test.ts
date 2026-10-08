import { test, expect } from "bun:test";
import { mkdtemp, cp, rm, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

for (const platform of ["darwin", "linux"]) {
  test(`installed bundle on ${platform} loads without source or node_modules`, async () => {
    const temp = await mkdtemp(join(tmpdir(), "macos plugin "));
    const client = new Client({ name: "macos-test", version: "1" });
    try {
      for (const dir of ["dist", "scripts", "lib"]) await cp(new URL("../" + dir, import.meta.url), join(temp, dir), { recursive: true });
      const bin = join(temp, "bin"); await mkdir(bin);
      for (const command of ["osascript", "screencapture"]) await writeFile(join(bin, command), "#!/bin/sh\necho synthetic-command-unavailable >&2\nexit 23\n", { mode: 0o755 });
      const env = Object.fromEntries(Object.entries(process.env).filter(([key, value]) => value !== undefined && !key.startsWith("MACOS_") && !key.startsWith("UTILS_"))) as Record<string,string>;
      Object.assign(env, { PATH: bin + ":" + env.PATH, MACOS_FORCE_PLATFORM: platform });
      await client.connect(new StdioClientTransport({ command: process.execPath, args: [join(temp, "dist/server.js")], cwd: temp, env, stderr: "pipe" }));
      const listed = await client.listTools();
      expect(listed.tools).toHaveLength(platform === "darwin" ? 64 : 1);
      const capability=await client.callTool({name:"macos_get_capabilities",arguments:{}});
      expect(capability.isError).toBe(false);
      expect(JSON.stringify(capability)).toContain("missing");
      if (platform === "darwin") {
        const rejected = await client.callTool({ name: "safari_close_tab", arguments: {} });
        expect(rejected.isError).toBe(true);
        expect(JSON.stringify(rejected)).toContain("confirm");
        const screenshot = await client.callTool({ name: "screenshot_full", arguments: { out: join(temp,"synthetic.png") } });
        expect(screenshot.isError).toBe(true);
        expect(screenshot.structuredContent).toEqual({stdout:"",stderr:"synthetic-command-unavailable\n",exit_code:23});
      }
    } finally { await client.close(); await rm(temp, {recursive:true,force:true}); }
  }, 60000);
}
