# macos

Claude Code and Codex plugin: a Bun MCP server (`src/`, bundled to `dist/server.js`) over JXA, EventKit, AppleScript and the system capture tools. Read [README.md](README.md) and [docs/productivity-api.md](docs/productivity-api.md) before you change a tool.

## Rules

- Writes select items by opaque ID. Display names from discovery are labels, never selectors.
- An update or delete needs `expected_revision` and `confirm=true`. A create needs an explicit container and a `request_key`, and a retry returns the first saved response. Keep all three contracts.
- Calendar and Reminders reads and writes go through EventKit and must not launch the apps.
- Never write a note body that came from a truncated result.
- `plugin.json` and `mcp.json` are the manifest sources. Do not hand-edit the generated `.claude-plugin/plugin.json`, `.mcp.json` or `dist/server.js`.
- Repository documents and code comments are English.

## Where to run things

In Loki's environment, run `bun install`, the build and the offline tests on `ssh sandbox` in a login shell (`bash -lc`). A native smoke test runs on the Mac, and it uses only temporary items that it deletes. It never edits personal notes, events or reminders.

## Verify

```sh
bun install --frozen-lockfile
bun run check
```

Build with the Bun version that CI uses (`bun-version` in `.github/workflows/check.yml`). Another version produces a different `dist/server.js`, and the CI diff step fails.

## Release

Release Please opens a release PR from the conventional commits. Merge it, then pin the new commit in [zyx1121/marketplace](https://github.com/zyx1121/marketplace) (see its AGENTS.md).
