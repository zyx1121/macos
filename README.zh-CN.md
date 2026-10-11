<!-- 翻译自 README.md @ docs/readme-template-v2。只翻译 "For AI agents" 之前的章节，英文版更新时一起改。 -->

<div align="center">

<h1>macOS</h1>

<p><strong>把备忘录、日历、提醒事项、邮件、Safari 和截图变成 agent 能用的 MCP 工具。</strong></p>

[![CI](https://img.shields.io/github/actions/workflow/status/zyx1121/macos/check.yml?branch=main&style=flat-square&label=CI)](https://github.com/zyx1121/macos/actions)
[![Release](https://img.shields.io/github/v/release/zyx1121/macos?style=flat-square&sort=semver)](https://github.com/zyx1121/macos/releases)
[![Claude Code](https://img.shields.io/badge/Claude_Code-plugin-D97757?style=flat-square)](https://github.com/zyx1121/marketplace)
[![License](https://img.shields.io/github/license/zyx1121/macos?style=flat-square)](LICENSE)

[English](README.md) | [繁體中文](README.zh-TW.md) | **简体中文**

</div>

```console
$ macos_get_capabilities
{"data": {"platform": "darwin", "tools": [ 64 tools, each with "available": true ],
  "permissions": {"calendar": "full_access", "reminders": "full_access", "screen_recording": "granted",
    "notes_automation": "target_not_running", "mail_automation": "granted", "safari_automation": "granted"}}}
```

你的计划大多记在备忘录、日历和提醒事项里。这个插件给 Codex 和 Claude Code 64 个操作原生应用的工具。日历和提醒事项通过 EventKit 操作，完全不会打开应用。

## 功能

- **读写备忘录**：账号、文件夹、搜索、新建、修改、追加和删除(13 个工具)。
- **用日历排程**：支持复杂重复规则、冲突检查和空闲时段查询，不会打开日历(14 个工具)。
- **管理提醒事项**：列表和待办，可搜索、完成，不会打开提醒事项(13 个工具)。
- **写邮件草稿、读取 Safari**：搜索邮件、编辑草稿(10 个工具)，标签页、网页文字和 JavaScript(8 个工具)。
- **截图**：全屏、指定区域、窗口或剪贴板(5 个工具)。

## 快速开始

```sh
claude plugin marketplace add zyx1121/marketplace
claude plugin install macos@zyx1121
```

Codex：先 `codex plugin marketplace add zyx1121/marketplace`，再 `codex plugin add macos@zyx1121`。开新的对话，问它“我明天有什么安排？”。

需要 macOS、Bun 和 uv。到“系统设置 > 隐私与安全性”给 MCP 主机这些权限：

- 日历和提醒事项的完全访问权限
- 备忘录、邮件和 Safari 的自动化权限
- 屏幕录制，给截图用

## 使用方法

| 类别 | 工具数 | 作用 |
|------|------:|------|
| 备忘录 | 13 | 账号和文件夹，以及列出、搜索、读取、新建、修改、追加和删除备忘录 |
| 日历 | 14 | 日历和来源、事件、重复规则、冲突和空闲时段 |
| 提醒事项 | 13 | 来源和列表，以及列出、搜索、读取、新建、修改、完成和删除待办 |
| 邮件 | 10 | 账号、邮箱、按 ID 或日期查询邮件，以及草稿 |
| Safari | 8 | 标签页、网页文字、选中内容和 JavaScript |
| 截图 | 5 | 全屏、区域、窗口、交互式和剪贴板截图 |
| 诊断 | 1 | `macos_get_capabilities`：工具可用性和权限状态 |

- 用口语提出要求，例如“读我的课程备忘录，把截止日期建成提醒事项”。由 agent 选择工具，server 不会自己猜截止日期或同步应用。
- 写入都用 ID。修改或删除需要 ID、`expected_revision` 和 `confirm=true`，发生冲突时先重新读取该项目。
- 新建需要明确的容器和 `request_key`，重试会返回第一次保存的结果。
- 完整的接口规范、名称和示例在 [docs/productivity-api.md](docs/productivity-api.md)。

## 配置

| 变量 | 作用 | 默认值 |
|------|------|--------|
| `MACOS_MCP_MAX_STRING_CHARS` | 结果中单个字符串的长度上限 | `20000` |
| `MACOS_MCP_MAX_TOTAL_CHARS` | 结果的总长度上限 | `120000` |
| `MACOS_MCP_STATE_DIR` | 新建重试记录的位置 | `~/Library/Application Support/zyx1121/macos/` |

被截断的地方都会标示。不要用截断过的内容覆盖备忘录。

## 工作原理

Bun 的 MCP server 按主机注册工具，缺少依赖的工具会隐藏，原因写在 stderr。备忘录通过 JXA 的 Apple Events 操作，所以可能在后台打开备忘录。日历和提醒事项的读写都用 EventKit。邮件、Safari 和截图用 AppleScript 和系统截图工具。`scripts/productivity.py OPERATION` 从 stdin 读取和 MCP 工具相同的 JSON。

## 限制

- 只支持 macOS。在 Linux 上只会注册诊断工具。
- 权限属于 MCP 主机应用，所以终端和桌面应用的权限可能不同。
- 备忘录的自动化可能会在后台打开备忘录。

## 其他

给 AI agent 的结构化信息与开发说明见[英文版](README.md#for-ai-agents)。

## 许可证

[MIT](LICENSE)
