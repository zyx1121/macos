/**
 * Tier A output schemas parsed against synthetic samples.
 *
 * The samples mirror the key set of real runs captured while writing these
 * schemas, with every value replaced by placeholder data — this repo is public,
 * so no real host, address or calendar name is committed.
 */
import { describe, expect, test } from "bun:test";
import { z } from "zod";
import { mapScriptOutput } from "../src/core/exec.ts";
import { allTools } from "../src/tools/index.ts";

function outputSchemaOf(name: string) {
  const tool = allTools.find((candidate) => candidate.name === name);
  if (!tool) throw new Error(`unknown tool: ${name}`);
  return z.object(tool.outputSchema);
}

const SAMPLES: Record<string, unknown> = {
  safari_get_url: { url: "https://example.test/page" },
  safari_get_title: { title: "Example Page" },
  safari_list_tabs: [{ wt: "1/1", title: "Example Page", url: "https://example.test/page" }],
  calendar_list_calendars: [
    { name: "Example Calendar", writable: true },
    { name: "Example Holidays", writable: false },
  ],
  reminders_list_lists: [{ name: "Example List" }],
  mail_list_accounts: [{ name: "Example", user: "user@example.test", addresses: "user@example.test, alias@example.test" }],

};

describe("Tier A output schemas", () => {
  for (const [name, data] of Object.entries(SAMPLES)) {
    test(`${name} accepts its real-world shape`, () => {
      const result = outputSchemaOf(name).safeParse({ data, metadata: { count: 1 } });
      expect(result.success ? null : result.error.issues).toBeNull();
    });

    test(`${name} tolerates keys added upstream`, () => {
      const widened = Array.isArray(data) ? [...(data as Record<string, unknown>[]).map((item) => ({ ...item, future_key: "x" }))] : { ...(data as Record<string, unknown>), future_key: "x" };
      const result = outputSchemaOf(name).safeParse({ data: widened, metadata: {} });
      expect(result.success).toBe(true);
    });
  }

  test("the truncation report is optional but accepted", () => {
    const schema = outputSchemaOf("reminders_list_lists");

    expect(schema.safeParse({ data: [{ name: "Example List" }], metadata: {} }).success).toBe(true);
    expect(
      schema.safeParse({
        data: [{ name: "Example List" }],
        metadata: {},
        _truncation: { fields: ["data[0].name"], original_chars: 999, limit: 100 },
      }).success,
    ).toBe(true);
  });

  test("Tier B tools still name the envelope shell", () => {
    const schema = outputSchemaOf("calendar_list_events");

    expect(schema.safeParse({ data: { anything: true }, metadata: {} }).success).toBe(true);
  });

  test("non-envelope tools declare the raw stream shell", () => {
    const schema = outputSchemaOf("screenshot_full");

    expect(schema.safeParse({ stdout: "", stderr: "", exit_code: 0 }).success).toBe(true);
    expect(schema.safeParse({ data: {}, metadata: {} }).success).toBe(false);
  });
});

/**
 * Regression guard for the failure path.
 *
 * The MCP client validates structuredContent against the declared schema even
 * when isError is set, and the generated JSON Schema forbids extra properties.
 * A failure shape that the tool's own schema rejects therefore reaches the
 * caller as a protocol error rather than a readable message. Caught by a live
 * smoke run against safari_get_url with no Safari window open.
 */
describe("failure paths satisfy their own output schema", () => {
  const run = (over: Partial<Parameters<typeof mapScriptOutput>[1]> = {}) => ({
    stdout: "",
    stderr: "",
    exitCode: 1,
    timedOut: false,
    timeoutMs: 1000,
    argv0: "example.py",
    ...over,
  });

  const CASES = {
    "script reported failure": run({ stdout: JSON.stringify({ success: false, error: { message: "boom", why: "because", hint: "do x" } }) }),
    "failure with bare message": run({ stdout: JSON.stringify({ success: false, error: { message: "boom" } }) }),
    "failure with no error detail": run({ stdout: JSON.stringify({ success: false }) }),
    "crash before any output": run({ stderr: "Traceback (most recent call last):", exitCode: 2 }),
    "json that is not an envelope": run({ stdout: JSON.stringify({ whatever: true }) }),
    "timeout": run({ timedOut: true, exitCode: -1 }),
  };

  // Script-backed tools only: utils_capabilities answers from memory and speaks neither shell.
  const scriptTools = allTools.filter((tool) => "data" in tool.outputSchema || "stdout" in tool.outputSchema);

  for (const tool of scriptTools) {
    const isEnvelope = "data" in tool.outputSchema;
    const schema = z.object(tool.outputSchema);

    for (const [label, scriptRun] of Object.entries(CASES)) {
      test(`${tool.name}: ${label}`, () => {
        const result = mapScriptOutput(isEnvelope, scriptRun);
        const parsed = schema.safeParse(result.structuredContent);

        expect(parsed.success ? null : { issues: parsed.error.issues, got: result.structuredContent }).toBeNull();
        expect(result.isError).toBe(true);
      });
    }
  }

  test("raw-shell tools keep their streams on a non-zero exit", () => {
    const result = mapScriptOutput(false, run({ stdout: "partial", stderr: "boom", exitCode: 3 }));

    expect(result.structuredContent).toEqual({ stdout: "partial", stderr: "boom", exit_code: 3 });
    expect(outputSchemaOf("screenshot_full").safeParse(result.structuredContent).success).toBe(true);
  });
});
