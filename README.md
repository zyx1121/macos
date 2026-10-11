<div align="center">

<h1>macOS</h1>

<p><strong>Notes, Calendar, Reminders, Mail, Safari and screenshots as MCP tools for your agent.</strong></p>

[![CI](https://img.shields.io/github/actions/workflow/status/zyx1121/macos/check.yml?branch=main&style=flat-square&label=CI)](https://github.com/zyx1121/macos/actions)
[![Release](https://img.shields.io/github/v/release/zyx1121/macos?style=flat-square&sort=semver)](https://github.com/zyx1121/macos/releases)
[![Claude Code](https://img.shields.io/badge/Claude_Code-plugin-D97757?style=flat-square)](https://github.com/zyx1121/marketplace)
[![License](https://img.shields.io/github/license/zyx1121/macos?style=flat-square)](LICENSE)

**English** | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md)

</div>

```console
$ macos_get_capabilities
{"data": {"platform": "darwin", "tools": [ 64 tools, each with "available": true ],
  "permissions": {"calendar": "full_access", "reminders": "full_access", "screen_recording": "granted",
    "notes_automation": "target_not_running", "mail_automation": "granted", "safari_automation": "granted"}}}
```

Your notes, calendar and reminders hold most of what you plan. This plugin gives Codex and Claude Code 64 tools for the native apps. Calendar and Reminders work through EventKit, so they never open the apps.

## Features

- **Reads and writes Notes**: accounts, folders, search, create, update, append and delete (13 tools).
- **Plans with Calendar**: events with complex recurrence, conflicts and free slots, without opening Calendar (14 tools).
- **Tracks Reminders**: lists and tasks, with search and completion, without opening Reminders (13 tools).
- **Drafts Mail and reads Safari**: message search and draft editing (10 tools), tabs, page text and JavaScript (8 tools).
- **Captures the screen**: full screen, a region, a window or the clipboard (5 tools).

## Quick start

```sh
claude plugin marketplace add zyx1121/marketplace
claude plugin install macos@zyx1121
```

Codex: `codex plugin marketplace add zyx1121/marketplace`, then `codex plugin add macos@zyx1121`. Open a new session and ask "What is on my calendar tomorrow?".

The plugin needs macOS, Bun and uv. In System Settings > Privacy & Security, give the MCP host these permissions:

- full access to Calendar and Reminders
- Automation for Notes, Mail and Safari
- Screen Recording, for screenshots

## Usage

| Family | Tools | Does |
|--------|------:|------|
| Notes | 13 | accounts and folders, and list, search, get, create, update, append and delete notes |
| Calendar | 14 | calendars and sources, occurrences, recurrence, conflicts and free slots |
| Reminders | 13 | sources and lists, and list, search, get, create, update, complete and delete tasks |
| Mail | 10 | accounts, mailboxes, messages by ID or date, and drafts |
| Safari | 8 | tabs, page text, the selection and JavaScript |
| Screenshot | 5 | full screen, region, window, interactive and clipboard captures |
| Diagnostics | 1 | `macos_get_capabilities`: tool availability and permission status |

- Ask in plain words, such as "read my coursework note and create reminders for its deadlines". The agent picks the tools. The server does not guess deadlines or sync apps by itself.
- Writes use IDs. An update or delete needs the ID, `expected_revision` and `confirm=true`. After a conflict, read the item again.
- A create needs an explicit container and a `request_key`. A retry returns the first saved response.
- The full contract, with names and examples, is in [docs/productivity-api.md](docs/productivity-api.md).

## Configuration

| Variable | Sets | Default |
|----------|------|---------|
| `MACOS_MCP_MAX_STRING_CHARS` | longest string in a result | `20000` |
| `MACOS_MCP_MAX_TOTAL_CHARS` | largest result | `120000` |
| `MACOS_MCP_STATE_DIR` | where create retry claims live | `~/Library/Application Support/zyx1121/macos/` |

Results mark each truncation. Never replace a note body with truncated content.

## How it works

The Bun MCP server registers the tools for the host and hides the ones with a missing dependency, with the reason on stderr. Notes uses Apple Events through JXA, so it can open Notes in the background. Calendar and Reminders use EventKit for reads and writes. Mail, Safari and screenshots use AppleScript and the system capture tools. `scripts/productivity.py OPERATION` takes the same JSON on stdin as the MCP tools.

## Limits

- macOS only. On Linux, only the diagnostics tool registers.
- The permissions belong to the MCP host app, so a terminal and a desktop app can differ.
- Notes automation can open Notes in the background.

## For AI agents

Facts for coding agents and LLM tools. The rules for changing the code are in [AGENTS.md](AGENTS.md).

- **Summary**: Claude Code and Codex plugin with 64 MCP tools for Notes, Calendar, Reminders, Mail, Safari and screenshots on macOS.
- **Type**: plugin
- **Interfaces**: MCP `macos` (stdio, `dist/server.js`). `scripts/productivity.py OPERATION` takes JSON on stdin.
- **Install**: `claude plugin install macos@zyx1121`, after `claude plugin marketplace add zyx1121/marketplace`
- **Run**: the host starts the MCP server
- **Verify**: call `macos_get_capabilities` and read the `permissions` object
- **Config**: `MACOS_MCP_MAX_STRING_CHARS`, `MACOS_MCP_MAX_TOTAL_CHARS`, `MACOS_MCP_STATE_DIR`
- **Secrets**: none. Retry claims stay in `~/Library/Application Support/zyx1121/macos/`.
- **Limits**: macOS only. Writes need IDs, `expected_revision` and `confirm=true`.

## Development

```sh
bun install --frozen-lockfile
bun run check
```

The offline tests never touch personal apps. Release Please opens the release PR, and the marketplace pins each release commit.

## License

[MIT](LICENSE)
