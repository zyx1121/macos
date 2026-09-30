import { test, expect } from "bun:test";
import { z } from "zod";
import { runScript } from "../src/core/exec.ts";
import { envelopeOutput, rawOutput } from "../src/core/schema.ts";

for (const envelope of [true, false]) {
  test(`missing script returns a schema-valid ${envelope ? 'envelope' : 'raw'} failure`, async () => {
    const result = await runScript({ script: "does-not-exist", args: [], envelope, timeoutMs: 100 });
    expect(result.isError).toBe(true);
    expect(z.object(envelope ? envelopeOutput() : rawOutput()).safeParse(result.structuredContent).success).toBe(true);
  });
}
