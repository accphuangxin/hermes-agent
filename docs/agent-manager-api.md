# hermes-agent-manager API 使用文档

> 版本：v0.1.0 | 更新日期：2026-06-04

---

## 架构概览

```
hermes-agent-manager (控制进程)
    │
    ├── ControlServer  :8640          ← 管理 API（本文档描述的接口）
    │
    ├── hermes profile "default"      ← 原生 profile（hermes gateway 管理）
    │     └── api_server  :8642/8643
    ├── hermes profile "health"       ← 原生 profile（hermes gateway 管理）
    │     └── api_server  :8645
    └── hermes profile "xxx"          ← 通过本 API 创建的新 profile
          └── api_server  :87xx
```

每个 Agent 本质上是一个 **hermes profile**：
- 拥有独立的 `~/.hermes/profiles/{name}/` 目录
- 独立的 `config.yaml`、`SOUL.md`、`memories/`、`skills/`
- 独立的 gateway 服务（launchd/systemd），开机自启
- 独立的 api_server 端口，对外暴露 OpenAI 兼容接口

---

## 服务管理命令

```bash
# 前台运行
hermes-agent-manager run --port 8640

# 安装为系统服务（launchd/systemd，开机自启）
hermes-agent-manager install --port 8640

# 服务控制
hermes-agent-manager start
hermes-agent-manager stop
hermes-agent-manager restart
hermes-agent-manager status    # 显示服务状态 + 所有 Agent 列表
hermes-agent-manager uninstall
```

**环境变量：**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AGENT_MANAGER_HOST` | `127.0.0.1` | 控制 API 绑定地址 |
| `AGENT_MANAGER_PORT` | `8640` | 控制 API 端口 |
| `AGENT_MANAGER_KEY` | 空（不鉴权） | Bearer token |
| `AGENT_MANAGER_DB` | `~/.hermes/agent_manager.db` | SQLite 路径 |

---

## 鉴权

所有接口（`/v1/health` 除外）需携带：

```
Authorization: Bearer <api-key>
```

`--api-key` 为空时跳过鉴权（本地开发用）。

---

## 接口总览

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/v1/health` | 健康检查 |
| `POST` | `/v1/agents` | 创建 Agent（创建 hermes profile + 别名 + 启动 gateway） |
| `GET` | `/v1/agents` | 列出所有 Agent（含原生 profile） |
| `GET` | `/v1/agents/{id}` | 获取单个 Agent 详情 |
| `PATCH` | `/v1/agents/{id}` | 更新 Agent 配置 |
| `DELETE` | `/v1/agents/{id}` | 删除 Agent（删除 hermes profile） |
| `POST` | `/v1/agents/{id}/start` | 启动 Agent gateway |
| `POST` | `/v1/agents/{id}/stop` | 停止 Agent gateway |
| `POST` | `/v1/agents/{id}/restart` | 重启 Agent gateway |
| `GET` | `/v1/agents/{id}/status` | 获取运行时状态快照 |

---

## GET /v1/health

健康检查，无需鉴权。

```bash
curl http://localhost:8640/v1/health
```

```json
{
  "status": "ok",
  "agents": 2,
  "running": 2,
  "time": 1748995200.0
}
```

---

## POST /v1/agents

创建一个新 Agent，底层调用 `hermes profile create`，完整流程：

1. 在 `~/.hermes/profiles/{name}/` 创建 profile 目录结构
2. 克隆 default profile 的配置（`config.yaml`、`skills/`，`.env` 不复制）
3. 写入 `SOUL.md`（如果传了 `soul`）
4. 写入 `api_server` 端口和 key 到 `config.yaml`
5. 创建别名脚本 `~/.local/bin/{name}` → `hermes -p {name} "$@"`
6. 安装并启动 gateway 服务（launchd / systemd）

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✓ | profile 名称，小写字母/数字/连字符/下划线 |
| `soul` | string | | 写入 `SOUL.md` 的人格定义 |
| `description` | string | | profile 描述，写入 `profile.yaml` |
| `clone` | bool | | 是否克隆 default 配置（默认 `true`，推荐） |
| `clone_from` | string | | 指定克隆来源 profile（默认从 default 克隆） |
| `api_server_port` | int | | api_server 端口，写入 `config.yaml` |
| `api_server_key` | string | | api_server Bearer token，写入 `config.yaml` |

**请求示例**

```bash
curl -X POST http://localhost:8640/v1/agents \
  -H "Content-Type: application/json" \
  -d '{
    "name": "customer-service",
    "description": "中文客服助手",
    "soul": "你是 Alice，友好专业的中文客服，只回答与订单、物流相关的问题。",
    "clone": true,
    "api_server_port": 8701,
    "api_server_key": "cs-token-123"
  }'
```

**响应示例**（201 Created）

```json
{
  "id": "hermes-profile-customer-service",
  "object": "agent",
  "name": "customer-service",
  "isDefault": false,
  "model": "gpt-5.5",
  "provider": "holdnimbus",
  "gatewayRunning": true,
  "skillCount": 25,
  "description": "中文客服助手",
  "apiServerPort": 8701,
  "apiServerKey": "cs-token-123",
  "source": "hermes-profile",
  "status": "running",
  "actual_port": 8701,
  "soul": "你是 Alice，友好专业的中文客服...",
  "meta": {}
}
```

创建完成后可直接通过别名操作该 Agent：

```bash
customer-service gateway status
customer-service gateway stop
customer-service chat -q "你好"
```

**错误码**

| 状态码 | 原因 |
|--------|------|
| `400` | `name` 为空或格式非法 |
| `409` | profile 名称已存在 |
| `500` | 创建失败（权限问题、gateway 安装失败等） |

---

## GET /v1/agents

列出所有 Agent，包含：
- hermes 原生 profile（`source: "hermes-profile"`）
- 通过本 API 创建的 profile（同为 `source: "hermes-profile"`）

`gatewayRunning` 通过实时 HTTP 探测 `/v1/health` 接口判断（不依赖 PID 文件）。

```bash
curl http://localhost:8640/v1/agents
```

**响应示例**

```json
{
  "agents": [
    {
      "id": "hermes-profile-default",
      "object": "agent",
      "name": "default",
      "isDefault": true,
      "model": "gpt-5.5",
      "provider": "holdnimbus",
      "gatewayRunning": true,
      "skillCount": 25,
      "description": "",
      "apiServerPort": 8643,
      "apiServerKey": "root@123123",
      "source": "hermes-profile",
      "status": "running",
      "actual_port": 8643,
      "soul": "..."
    },
    {
      "id": "hermes-profile-health",
      "object": "agent",
      "name": "health",
      "isDefault": false,
      "model": "qwen3_6",
      "provider": "custom",
      "gatewayRunning": true,
      "skillCount": 2,
      "description": "个人健康管家，负责每日健康打卡...",
      "apiServerPort": 8645,
      "apiServerKey": "root@123123",
      "source": "hermes-profile",
      "status": "running",
      "actual_port": 8645,
      "soul": "..."
    }
  ],
  "total": 2,
  "running": 2
}
```

**响应字段说明**

| 字段 | 说明 |
|------|------|
| `id` | `hermes-profile-{name}` |
| `isDefault` | 是否为 default profile |
| `model` | 当前使用的模型 |
| `provider` | 模型提供商 |
| `gatewayRunning` | gateway 是否在线（HTTP 实时探测） |
| `skillCount` | 已安装技能数量 |
| `apiServerPort` | api_server 监听端口 |
| `apiServerKey` | api_server Bearer token |
| `soul` | `SOUL.md` 内容 |
| `source` | `hermes-profile`（所有 Agent 均来自 hermes profile） |
| `status` | `running` / `stopped` |

---

## GET /v1/agents/{id}

获取单个 Agent 详情，`id` 格式为 `hermes-profile-{name}`。

```bash
curl http://localhost:8640/v1/agents/hermes-profile-health
```

**错误码**

| 状态码 | 原因 |
|--------|------|
| `404` | Agent 不存在 |

---

## PATCH /v1/agents/{id}

更新 Agent 配置，支持所有 hermes profile Agent（`hermes-profile-{name}`）。

配置写入文件后自动在后台重启该 Agent 的 gateway，无需手动操作。

**请求体（所有字段可选，只传需要修改的）**

| 字段 | 类型 | 写入目标 | 说明 |
|------|------|----------|------|
| `soul` | string | `SOUL.md` | Agent 人格/系统提示词 |
| `description` | string | `profile.yaml` | Agent 描述 |
| `api_server_port` | int | `config.yaml` `platforms.api_server.extra.port` | api_server 监听端口 |
| `api_server_key` | string | `config.yaml` `platforms.api_server.extra.key` | api_server Bearer token |
| `model` | string | `config.yaml` `model.default` | 使用的模型名称 |
| `provider` | string | `config.yaml` `model.provider` | 模型提供商 |

**修改人格（soul）**

```bash
curl -X PATCH http://localhost:8640/v1/agents/hermes-profile-customer-service \
  -H "Content-Type: application/json" \
  -d '{
    "soul": "你是 Alice，友好专业的中文客服，只回答与订单、物流相关的问题。遇到无法回答的问题请礼貌转人工。"
  }'
```

**修改端口**

```bash
curl -X PATCH http://localhost:8640/v1/agents/hermes-profile-purchasing-agent \
  -H "Content-Type: application/json" \
  -d '{"api_server_port": 8710}'
```

**修改模型**

```bash
curl -X PATCH http://localhost:8640/v1/agents/hermes-profile-customer-service \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-v4-pro",
    "provider": "tencentmaas"
  }'
```

**同时修改多个字段**

```bash
curl -X PATCH http://localhost:8640/v1/agents/hermes-profile-customer-service \
  -H "Content-Type: application/json" \
  -d '{
    "soul": "你是 Alice，专业的中文客服助手。",
    "description": "售后客服专员",
    "model": "gpt-5.5",
    "provider": "holdnimbus",
    "api_server_port": 8702,
    "api_server_key": "new-token-456"
  }'
```

**响应示例**（200 OK）

```json
{
  "id": "hermes-profile-customer-service",
  "object": "agent",
  "name": "customer-service",
  "isDefault": false,
  "model": "gpt-5.5",
  "provider": "holdnimbus",
  "gatewayRunning": true,
  "skillCount": 25,
  "description": "售后客服专员",
  "apiServerPort": 8702,
  "apiServerKey": "new-token-456",
  "source": "hermes-profile",
  "status": "running",
  "actual_port": 8702,
  "soul": "你是 Alice，专业的中文客服助手。",
  "meta": {}
}
```

> gateway 在后台异步重启，响应返回时重启可能尚未完成，几秒后通过 `/v1/agents/{id}/status` 确认 `gatewayRunning: true`。

**错误码**

| 状态码 | 原因 |
|--------|------|
| `404` | Agent 不存在 |
| `500` | 配置写入失败 |

---

## DELETE /v1/agents/{id}

删除 Agent，底层调用 `hermes profile delete`，会同时：
- 停止并卸载 gateway 服务
- 删除 `~/.hermes/profiles/{name}/` 目录
- 删除别名脚本 `~/.local/bin/{name}`

**不能删除 default profile。**

```bash
curl -X DELETE http://localhost:8640/v1/agents/hermes-profile-customer-service
```

**响应示例**

```json
{"deleted": "customer-service"}
```

**错误码**

| 状态码 | 原因 |
|--------|------|
| `400` | 尝试删除 default profile |
| `404` | Profile 不存在 |
| `500` | 删除失败 |

---

## POST /v1/agents/{id}/start

启动指定 Agent 的 gateway，等价于 `hermes -p {name} gateway start`。

```bash
curl -X POST http://localhost:8640/v1/agents/hermes-profile-customer-service/start
```

---

## POST /v1/agents/{id}/stop

停止指定 Agent 的 gateway，等价于 `hermes -p {name} gateway stop`。

```bash
curl -X POST http://localhost:8640/v1/agents/hermes-profile-customer-service/stop
```

---

## POST /v1/agents/{id}/restart

重启指定 Agent 的 gateway，等价于 `hermes -p {name} gateway restart`。

```bash
curl -X POST http://localhost:8640/v1/agents/hermes-profile-customer-service/restart
```

---

## GET /v1/agents/{id}/status

获取 Agent 运行时状态快照（轻量接口）。

```bash
curl http://localhost:8640/v1/agents/hermes-profile-customer-service/status
```

```json
{
  "id": "hermes-profile-customer-service",
  "name": "customer-service",
  "status": "running",
  "actual_port": 8701,
  "started_at": 1748995200.0,
  "error": ""
}
```

---

## 每个 Agent 对外的 API（各自独立端口）

每个 Agent 的 api_server 端口暴露完整的 OpenAI 兼容接口，鉴权使用 `apiServerKey`。

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/chat/completions` | OpenAI Chat Completions（流式/非流式） |
| `POST` | `/v1/responses` | OpenAI Responses API |
| `GET` | `/v1/models` | 列出可用模型 |
| `GET` | `/v1/capabilities` | 能力声明 |
| `POST` | `/api/sessions` | 创建会话 |
| `GET` | `/api/sessions` | 列出会话 |
| `POST` | `/api/sessions/{id}/chat` | 会话聊天（同步） |
| `POST` | `/api/sessions/{id}/chat/stream` | 会话聊天（SSE 流式） |
| `POST` | `/api/sessions/{id}/fork` | 分叉会话 |
| `POST` | `/v1/runs` | 异步运行 |
| `GET` | `/v1/runs/{run_id}/events` | 运行事件流（SSE） |
| `GET` | `/health` | 健康检查 |

**发送消息示例**

```bash
# 非流式
curl -X POST http://localhost:8701/v1/chat/completions \
  -H "Authorization: Bearer cs-token-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "hermes-agent",
    "messages": [{"role": "user", "content": "我的订单什么时候到？"}]
  }'

# 流式
curl -X POST http://localhost:8701/v1/chat/completions \
  -H "Authorization: Bearer cs-token-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "hermes-agent",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": true
  }'
```

---

## 完整工作流示例

```bash
BASE="http://localhost:8640"

# 1. 查看当前所有 Agent
curl -s $BASE/v1/agents | python3 -m json.tool

# 2. 创建新 Agent（自动克隆配置、创建别名、安装并启动 gateway）
curl -s -X POST $BASE/v1/agents \
  -H "Content-Type: application/json" \
  -d '{
    "name": "customer-service",
    "description": "中文客服助手",
    "soul": "你是友好的中文客服，专注解决订单和物流问题。",
    "clone": true,
    "api_server_port": 8701,
    "api_server_key": "cs-token-123"
  }' | python3 -m json.tool

# 3. 等待 gateway 启动完成
sleep 3
curl http://localhost:8701/v1/health

# 4. 与新 Agent 对话
curl -X POST http://localhost:8701/v1/chat/completions \
  -H "Authorization: Bearer cs-token-123" \
  -H "Content-Type: application/json" \
  -d '{"model":"hermes-agent","messages":[{"role":"user","content":"你好"}]}'

# 5. 通过别名直接操作
customer-service gateway status
customer-service chat -q "今天物流怎么样"

# 6. 停止 / 启动 / 重启
curl -X POST $BASE/v1/agents/hermes-profile-customer-service/stop
curl -X POST $BASE/v1/agents/hermes-profile-customer-service/start
curl -X POST $BASE/v1/agents/hermes-profile-customer-service/restart

# 7. 删除 Agent（同时清理 profile 目录、别名、服务）
curl -X DELETE $BASE/v1/agents/hermes-profile-customer-service
```

---

## 错误响应格式

```json
{"error": "错误描述信息"}
```

| 状态码 | 含义 |
|--------|------|
| `400` | 请求参数错误 |
| `401` | 鉴权失败 |
| `404` | Agent 不存在 |
| `409` | 状态冲突（profile 已存在、运行中更新等） |
| `500` | 服务端错误 |

---

## 相关文件

| 路径 | 说明 |
|------|------|
| `~/.hermes/profiles/{name}/` | Agent profile 目录 |
| `~/.hermes/profiles/{name}/SOUL.md` | 人格定义 |
| `~/.hermes/profiles/{name}/config.yaml` | 模型、api_server、工具配置 |
| `~/.hermes/profiles/{name}/skills/` | 已安装技能 |
| `~/.hermes/profiles/{name}/memories/` | 长期记忆 |
| `~/.local/bin/{name}` | 别名脚本（`hermes -p {name} "$@"`） |
| `~/.hermes/logs/agent_manager.log` | 管理器日志 |
| `~/.hermes/agent_manager.db` | 管理器 SQLite 数据库 |
| `~/.hermes/agent_manager.pid` | 管理器 PID 文件 |
