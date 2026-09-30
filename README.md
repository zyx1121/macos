# macOS

Calendar, Reminders, Mail, Safari and screen capture through 28 native MCP tools.

An independent plugin for Codex and Claude Code. Ask your agent to perform the
task; MCP is the public interface and scripts are the implementation. Extracted
from [zyx1121/plugin](https://github.com/zyx1121/plugin).

## Install

Requires Bun (tested with 1.3.13) and uv on the host PATH.

```sh
# Claude Code
claude plugin marketplace add zyx1121/marketplace
claude plugin install macos@zyx1121

# Codex
codex plugin marketplace add zyx1121/marketplace
codex plugin add macos@zyx1121
```

Restart the client session after installation. The committed `dist/server.js`
bundle needs no `bun install` in the plugin cache. Both manifests are generated
from `plugin.json` and `mcp.json`; the marketplace pins release commits.

## Use

Ask your agent to list calendars, find a reminder, read a Mail message, inspect
Safari tabs, or capture a specified region of the screen.

| Family | Tools | Behavior |
|---|---:|---|
| Calendar | 5 | List calendars/events, search, add and delete events |
| Reminders | 5 | List, add, complete and delete reminders |
| Mail | 5 | List accounts/inbox, search/read messages and compose a visible draft |
| Safari | 8 | Inspect tabs/page/selection, open/close a tab and evaluate JavaScript |
| Screenshot | 5 | Full screen, interactive area/window, fixed region and clipboard |

All tools require macOS. Calendar, Reminders, Mail and Safari require uv and
osascript; screenshot tools require screencapture. Missing dependencies hide
only the affected tools, with reasons on stderr. Linux exposes an empty tool list.

Calendar and Reminders reads use EventKit and do not launch the applications.
Grant the calling terminal or host Calendar and Reminders access in macOS privacy
settings. App writes and Mail/Safari automation need the corresponding Automation
permission. Screen capture needs Screen Recording access. Safari JavaScript
requires Develop > Allow JavaScript from Apple Events.

Calendar deletion, reminder completion/deletion and Safari tab closing retain
`confirm: true`. Mail only composes visible drafts; it never sends mail.
Safari operates on the live browser, and JavaScript can change the current page.
Interactive screenshot area/window tools wait for the user; clipboard capture
overwrites the clipboard. File captures default to `/tmp/screenshot.png`.

Calendar and reminder dates retain the existing English AppleScript format so
consumers such as today-mod continue to parse them.

## Migration

Install `macos@zyx1121` before updating zyx to 0.27.0. Short tool names,
parameters, output schemas and confirmation gates are preserved. Claude Code's
provider changes from `plugin_zyx_utils` to `plugin_macos_macos`. Remove any
manual registration of the same server to avoid duplicates.

Update today-mod to 0.3.0 to resolve the installed macos and nycu script paths.

## Development

```sh
bun install --frozen-lockfile
bun run check
claude plugin validate .
```

Tests are offline: synthetic results, fake executables, isolated bundled MCP
sessions and EventKit date-format compatibility. They do not modify live apps,
accounts or personal files.

`MACOS_MCP_MAX_STRING_CHARS` and `MACOS_MCP_MAX_TOTAL_CHARS` control
output truncation (defaults 20000/120000); the corresponding `UTILS_` names remain
fallbacks. `MACOS_FORCE_PLATFORM` is a registration-test override and does
not emulate another operating system.

- `src/`: MCP schemas, host checks and subprocess execution
- `scripts/`, `lib/`: domain implementation
- `dist/server.js`: standalone bundled runtime
- `plugin.json`, `mcp.json`: portable manifests
- `.claude-plugin/plugin.json`, `.mcp.json`: generated Claude Code compatibility

## License

[MIT](LICENSE)
