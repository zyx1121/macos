<!-- 翻譯自 README.md @ docs/readme-template-v2。只翻 "For AI agents" 以上的章節，英文版更新時一起改。 -->

<div align="center">

<h1>macOS</h1>

<p><strong>把備忘錄、行事曆、提醒事項、郵件、Safari 和截圖變成 agent 能用的 MCP 工具。</strong></p>

[![CI](https://img.shields.io/github/actions/workflow/status/zyx1121/macos/check.yml?branch=main&style=flat-square&label=CI)](https://github.com/zyx1121/macos/actions)
[![Release](https://img.shields.io/github/v/release/zyx1121/macos?style=flat-square&sort=semver)](https://github.com/zyx1121/macos/releases)
[![Claude Code](https://img.shields.io/badge/Claude_Code-plugin-D97757?style=flat-square)](https://github.com/zyx1121/marketplace)
[![License](https://img.shields.io/github/license/zyx1121/macos?style=flat-square)](LICENSE)

[English](README.md) | **繁體中文** | [简体中文](README.zh-CN.md)

</div>

```console
$ macos_get_capabilities
{"data": {"platform": "darwin", "tools": [ 64 tools, each with "available": true ],
  "permissions": {"calendar": "full_access", "reminders": "full_access", "screen_recording": "granted",
    "notes_automation": "target_not_running", "mail_automation": "granted", "safari_automation": "granted"}}}
```

你的計畫大多記在備忘錄、行事曆和提醒事項裡。這個 plugin 給 Codex 和 Claude Code 64 個操作原生 App 的工具。行事曆和提醒事項透過 EventKit 操作，完全不會打開 App。

## 功能

- **讀寫備忘錄**：帳號、資料夾、搜尋、新增、修改、附加和刪除(13 個工具)。
- **用行事曆排程**：支援複雜重複規則、衝突檢查和空檔查詢，不會打開行事曆(14 個工具)。
- **管理提醒事項**：清單和待辦，可搜尋、完成，不會打開提醒事項(13 個工具)。
- **寫郵件草稿、讀 Safari**：搜尋郵件、編輯草稿(10 個工具)，分頁、網頁文字和 JavaScript(8 個工具)。
- **截圖**：全螢幕、指定區域、視窗或剪貼簿(5 個工具)。

## 快速開始

```sh
claude plugin marketplace add zyx1121/marketplace
claude plugin install macos@zyx1121
```

Codex：先 `codex plugin marketplace add zyx1121/marketplace`，再 `codex plugin add macos@zyx1121`。開新的對話，問它「我明天有什麼行程？」。

需要 macOS、Bun 和 uv。到「系統設定 > 隱私權與安全性」給 MCP 主機這些權限：

- 行事曆和提醒事項的完整取用權
- 備忘錄、郵件和 Safari 的自動化權限
- 螢幕錄製，給截圖用

## 使用方式

| 類別 | 工具數 | 作用 |
|------|------:|------|
| 備忘錄 | 13 | 帳號和資料夾，以及列出、搜尋、讀取、新增、修改、附加和刪除備忘錄 |
| 行事曆 | 14 | 行事曆和來源、事件、重複規則、衝突和空檔 |
| 提醒事項 | 13 | 來源和清單，以及列出、搜尋、讀取、新增、修改、完成和刪除待辦 |
| 郵件 | 10 | 帳號、信箱、依 ID 或日期查郵件，以及草稿 |
| Safari | 8 | 分頁、網頁文字、選取內容和 JavaScript |
| 截圖 | 5 | 全螢幕、區域、視窗、互動式和剪貼簿截圖 |
| 診斷 | 1 | `macos_get_capabilities`：工具可用性和權限狀態 |

- 用口語提出要求，例如「讀我的課程備忘錄，把截止日建成提醒事項」。由 agent 挑工具，server 不會自己猜截止日或同步 App。
- 寫入都用 ID。修改或刪除需要 ID、`expected_revision` 和 `confirm=true`，發生衝突時先重新讀取該項目。
- 新增需要明確的容器和 `request_key`，重試會回傳第一次存好的結果。
- 完整的介面規格、名稱和範例在 [docs/productivity-api.md](docs/productivity-api.md)。

## 設定

| 變數 | 作用 | 預設 |
|------|------|------|
| `MACOS_MCP_MAX_STRING_CHARS` | 結果中單一字串的長度上限 | `20000` |
| `MACOS_MCP_MAX_TOTAL_CHARS` | 結果的總長度上限 | `120000` |
| `MACOS_MCP_STATE_DIR` | 新增重試紀錄的位置 | `~/Library/Application Support/zyx1121/macos/` |

被截斷的地方都會標示。不要用截斷過的內容覆寫備忘錄。

## 運作方式

Bun 的 MCP server 依主機註冊工具，缺少相依套件的工具會隱藏，原因寫在 stderr。備忘錄透過 JXA 的 Apple Events 操作，所以可能在背景打開備忘錄。行事曆和提醒事項的讀寫都用 EventKit。郵件、Safari 和截圖用 AppleScript 和系統截圖工具。`scripts/productivity.py OPERATION` 從 stdin 讀取和 MCP 工具相同的 JSON。

## 限制

- 只支援 macOS。在 Linux 上只會註冊診斷工具。
- 權限屬於 MCP 主機 App，所以終端機和桌面 App 的權限可能不同。
- 備忘錄的自動化可能會在背景打開備忘錄。

## 其他

給 AI agent 的結構化資訊與開發說明在[英文版](README.md#for-ai-agents)。

## 授權

[MIT](LICENSE)
