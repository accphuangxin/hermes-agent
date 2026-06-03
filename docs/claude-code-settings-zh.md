# Claude Code 配置属性完整说明

> 最后更新：2026-06-02
> 配置文件路径：`~/.claude/settings.json`（全局）或 `.claude/settings.json`（项目）

---

## 目录

1. [配置文件一览](#配置文件一览)
2. [模型设置](#模型设置)
3. [权限设置](#权限设置)
4. [UI 与交互](#ui-与交互)
5. [内存与会话](#内存与会话)
6. [MCP 服务器](#mcp-服务器)
7. [沙箱隔离](#沙箱隔离)
8. [Git 与归因](#git-与归因)
9. [Worktree 设置](#worktree-设置)
10. [其他设置](#其他设置)
11. [keybindings.json 快捷键](#keybindingsjson-快捷键)
12. [.mcp.json 服务器配置](#mcpjson-服务器配置)
13. [配置优先级](#配置优先级)
14. [常用示例](#常用示例)

---

## 配置文件一览

| 文件 | 作用域 | 路径 | 说明 |
|------|--------|------|------|
| `settings.json` | 用户全局 | `~/.claude/settings.json` | 所有项目生效 |
| `settings.json` | 项目共享 | `.claude/settings.json` | 提交到 git，团队共用 |
| `settings.local.json` | 项目本地 | `.claude/settings.local.json` | 不提交 git，个人覆盖 |
| `managed-settings.json` | 组织级 | 系统目录 | 组织强制配置，只读 |
| `keybindings.json` | 用户全局 | `~/.claude/keybindings.json` | 键盘快捷键 |
| `.mcp.json` | 项目 | 项目根目录 | MCP 服务器（团队共享） |
| `~/.claude.json` | 用户 | `~` | MCP 服务器（用户私有） |

---

## 模型设置

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model` | string | 系统默认 | 默认使用的模型。可选：`claude-sonnet-4-6`、`claude-opus-4-6`、`claude-haiku-4-5` |
| `availableModels` | array | 无限制 | 限制用户可选的模型列表，如 `["sonnet", "haiku"]` |
| `effortLevel` | string | - | 推理强度：`low` / `medium` / `high` / `xhigh` |
| `alwaysThinkingEnabled` | boolean | `false` | 默认启用扩展思考（Extended Thinking）模式 |
| `showThinkingSummaries` | boolean | `false` | 会话中显示扩展思考摘要 |
| `modelOverrides` | object | `{}` | 映射 Anthropic 模型 ID 到提供商特定 ID（Bedrock ARN、Vertex ID 等） |

---

## 权限设置

```json
{
  "permissions": {
    "allow": [],
    "deny": [],
    "ask": [],
    "additionalDirectories": [],
    "defaultMode": "default"
  }
}
```

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `permissions.allow` | array | `[]` | 自动允许的工具规则，无需确认 |
| `permissions.deny` | array | `[]` | 永久拒绝的工具规则 |
| `permissions.ask` | array | `[]` | 每次都需要用户确认的规则 |
| `permissions.additionalDirectories` | array | `[]` | 额外允许 Claude 访问的目录路径 |
| `permissions.defaultMode` | string | `"default"` | 默认权限模式（见下表） |
| `permissions.disableBypassPermissionsMode` | string | - | 设为 `"disable"` 禁止使用 bypass 模式 |
| `permissions.skipDangerousModePermissionPrompt` | boolean | `false` | 跳过危险模式的确认提示 |

**defaultMode 可选值：**

| 值 | 说明 |
|----|------|
| `default` | 标准模式，危险操作需确认 |
| `acceptEdits` | 自动接受文件编辑，其他操作仍需确认 |
| `plan` | 只规划不执行 |
| `auto` | 自动执行所有操作 |
| `bypassPermissions` | 跳过所有权限检查（危险，仅限可信环境） |

**权限规则语法：**

```
Bash(npm run *)           # 匹配 npm run 开头的命令
Bash(git *)               # 匹配所有 git 命令
Read(./src/**)            # 允许读取 src 目录
Edit(./src/**)            # 允许编辑 src 目录
WebFetch(domain:x.com)    # 限制特定域名
Read(./.env)              # 禁止读取 .env 文件（用在 deny 里）
```

---

## UI 与交互

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `tui` | string | `"default"` | 界面模式：`default`（标准）/ `fullscreen`（全屏） |
| `editorMode` | string | `"normal"` | 编辑器模式：`normal` / `vim` |
| `viewMode` | string | `"default"` | 视图模式：`default` / `verbose`（详细）/ `focus`（专注） |
| `autoScrollEnabled` | boolean | `true` | 全屏模式下自动滚动到最新内容 |
| `syntaxHighlightingDisabled` | boolean | `false` | 禁用代码语法高亮 |
| `prefersReducedMotion` | boolean | `false` | 减少/禁用动画效果 |
| `showTurnDuration` | boolean | `true` | 显示每轮响应的耗时 |
| `spinnerTipsEnabled` | boolean | `true` | 加载时显示提示信息 |
| `terminalProgressBarEnabled` | boolean | `true` | 显示进度条 |
| `preferredNotifChannel` | string | `"auto"` | 通知方式：`auto` / `terminal_bell` / `iterm2` |
| `language` | string | - | 响应语言：`english` / `chinese` / `japanese` / `spanish` 等 |

---

## 内存与会话

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `autoMemoryEnabled` | boolean | `true` | 启用跨会话自动记忆（agent 自动保存和读取记忆） |
| `autoMemoryDirectory` | string | - | 自定义记忆文件的存储路径 |
| `cleanupPeriodDays` | number | `30` | 会话文件保留天数，最小值 1 |
| `awaySummaryEnabled` | boolean | `true` | 长时间离开后返回时显示会话摘要 |
| `claudeMdExcludes` | array | - | 排除特定 CLAUDE.md 文件的 glob 模式列表 |

---

## MCP 服务器

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enableAllProjectMcpServers` | boolean | `false` | 自动批准 `.mcp.json` 中的所有服务器 |
| `enabledMcpjsonServers` | array | - | 明确允许加载的 MCP 服务器名称列表 |
| `disabledMcpjsonServers` | array | - | 明确禁用的 MCP 服务器名称列表 |

---

## 沙箱隔离

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `sandbox.enabled` | boolean | `false` | 启用沙箱隔离（限制文件系统和网络访问） |
| `sandbox.failIfUnavailable` | boolean | `false` | 沙箱不可用时直接失败（而不是降级运行） |
| `sandbox.autoAllowBashIfSandboxed` | boolean | `true` | 沙箱环境中自动允许 Bash 命令 |
| `sandbox.excludedCommands` | array | - | 排除在沙箱外执行的命令列表 |
| `sandbox.filesystem.allowWrite` | array | - | 沙箱内允许写入的路径列表 |
| `sandbox.filesystem.denyWrite` | array | - | 沙箱内禁止写入的路径列表 |
| `sandbox.filesystem.denyRead` | array | - | 沙箱内禁止读取的路径列表 |
| `sandbox.network.allowLocalBinding` | boolean | `false` | 允许绑定本地端口 |

---

## Git 与归因

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `attribution.commit` | string | `"🤖 Generated with Claude Code"` | 提交消息末尾追加的归因文本 |
| `attribution.pr` | string | `""` | PR 正文末尾追加的归因文本 |
| `includeGitInstructions` | boolean | `true` | 是否在系统提示中包含 Git 操作指导 |
| `prUrlTemplate` | string | - | PR URL 模板，支持 `{{.Owner}}`、`{{.Repo}}`、`{{.Number}}` |

---

## Worktree 设置

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `worktree.baseRef` | string | `"fresh"` | 基础分支：`fresh`（空白分支）/ `head`（当前分支） |
| `worktree.symlinkDirectories` | array | `[]` | 在 worktree 中创建符号链接的目录 |
| `worktree.sparsePaths` | array | - | Sparse checkout 包含的目录 |
| `worktree.bgIsolation` | string | `"worktree"` | 后台隔离模式：`worktree` / `none` |

---

## 其他设置

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `env` | object | `{}` | 注入到 Claude Code 进程的环境变量 |
| `hooks` | object | `{}` | 自动化钩子配置（PreToolUse / PostToolUse / SessionStart 等） |
| `hooks_auto_accept` | boolean | `false` | 自动接受新发现的钩子，无需确认 |
| `autoUpdatesChannel` | string | `"latest"` | 自动更新渠道：`stable` / `latest` |
| `minimumVersion` | string | - | 要求的最低 Claude Code 版本，如 `"2.1.100"` |
| `respectGitignore` | boolean | `true` | `@` 文件选择器是否遵守 .gitignore |
| `disableWorkflows` | boolean | `false` | 禁用动态 workflows 功能 |
| `plansDirectory` | string | `~/.claude/plans` | 计划文件（Plan 模式）的存储目录 |
| `fastModePerSessionOptIn` | boolean | `false` | 每个会话单独开启快速模式 |
| `feedbackSurveyRate` | number | - | 质量调查出现概率（0~1） |

**常用环境变量（在 `env` 中设置）：**

| 变量 | 说明 |
|------|------|
| `ANTHROPIC_MODEL` | 覆盖默认模型 ID |
| `ENABLE_TOOL_SEARCH` | 工具搜索：`true` / `false` / `auto` |
| `MCP_TIMEOUT` | MCP 服务器启动超时（毫秒） |
| `MAX_MCP_OUTPUT_TOKENS` | MCP 工具输出 token 上限 |
| `CLAUDE_CODE_ENABLE_TELEMETRY` | `1` 启用遥测数据上报 |

---

## keybindings.json 快捷键

**路径：** `~/.claude/keybindings.json`

### 常用快捷键

#### Chat（聊天输入）

| 默认快捷键 | 操作 | 说明 |
|-----------|------|------|
| `Enter` | `chat:submit` | 提交消息 |
| `Ctrl+J` | `chat:newline` | 插入换行 |
| `Escape` | `chat:cancel` | 取消输入 |
| `Ctrl+L` | `chat:clearInput` | 清空输入框 |
| `Ctrl+G` | `chat:externalEditor` | 打开外部编辑器 |
| `Ctrl+S` | `chat:stash` | 暂存当前输入 |
| `Ctrl+V` | `chat:imagePaste` | 粘贴图像 |
| `Meta+P` | `chat:modelPicker` | 打开模型选择器 |
| `Shift+Tab` | `chat:cycleMode` | 循环切换权限模式 |
| `Meta+O` | `chat:fastMode` | 切换快速模式 |
| `Meta+T` | `chat:thinkingToggle` | 切换扩展思考 |

#### App（全局）

| 默认快捷键 | 操作 | 说明 |
|-----------|------|------|
| `Ctrl+C` | `app:interrupt` | 中断当前操作 |
| `Ctrl+D` | `app:exit` | 退出 Claude Code |
| `Ctrl+T` | `app:toggleTodos` | 显示/隐藏任务列表 |
| `Ctrl+O` | `app:toggleTranscript` | 显示详细对话记录 |
| `Ctrl+R` | `history:search` | 搜索历史消息 |

### 配置格式

```json
{
  "bindings": [
    {
      "context": "Chat",
      "bindings": {
        "ctrl+enter": "chat:submit",
        "ctrl+s": null
      }
    }
  ]
}
```

**按键语法：**
- `ctrl+k`、`shift+tab`、`meta+p`（Alt/Option）、`cmd+s`
- 和弦绑定：`ctrl+k ctrl+s`（依次按下）
- 解绑：将值设为 `null`

---

## .mcp.json 服务器配置

**路径：** 项目根目录 `.mcp.json`

### HTTP 服务器

```json
{
  "mcpServers": {
    "my-api": {
      "type": "http",
      "url": "https://api.example.com/mcp/",
      "headers": {
        "Authorization": "Bearer ${API_TOKEN}"
      },
      "timeout": 30000
    }
  }
}
```

### Stdio 本地服务器

```json
{
  "mcpServers": {
    "local-tool": {
      "type": "stdio",
      "command": "node",
      "args": ["./mcp-server.js"],
      "env": {
        "DB_URL": "${DATABASE_URL}"
      }
    }
  }
}
```

| 字段 | 说明 |
|------|------|
| `type` | `http` / `streamable-http` / `stdio` / `ws` |
| `url` | HTTP 服务器地址（支持 `${VAR}` 环境变量） |
| `command` | stdio 模式的可执行程序 |
| `args` | 命令行参数 |
| `env` | 环境变量 |
| `headers` | HTTP 请求头 |
| `timeout` | 工具执行超时（毫秒） |
| `alwaysLoad` | `true` = 始终加载到上下文，不等工具搜索 |

---

## 配置优先级

从高到低：

1. `managed-settings.json`（组织托管，只读）
2. `.claude/settings.local.json`（项目本地，不提交 git）
3. `.claude/settings.json`（项目共享，提交 git）
4. `~/.claude/settings.json`（用户全局）

**合并规则：**
- 权限规则（allow / deny / ask）：**叠加**（所有层级的规则都生效）
- 其他字段：**覆盖**（高优先级覆盖低优先级）

---

## 常用示例

### 团队项目配置（.claude/settings.json）

```json
{
  "model": "claude-sonnet-4-6",
  "permissions": {
    "allow": [
      "Bash(npm run *)",
      "Bash(git *)",
      "Read(.)"
    ],
    "deny": [
      "Bash(rm -rf *)",
      "Read(.env)"
    ],
    "defaultMode": "acceptEdits"
  }
}
```

### 个人全局配置（~/.claude/settings.json）

```json
{
  "editorMode": "vim",
  "language": "chinese",
  "autoMemoryEnabled": true,
  "cleanupPeriodDays": 60,
  "permissions": {
    "allow": [
      "Bash(git *)",
      "Bash(npm *)"
    ]
  }
}
```

### 减少权限提示

```json
{
  "permissions": {
    "defaultMode": "acceptEdits",
    "allow": [
      "Bash(*)",
      "Read(**)",
      "Edit(**)"
    ]
  }
}
```
