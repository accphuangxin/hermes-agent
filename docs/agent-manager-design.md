# Agent Manager 设计方案（方案B：独立端口）

> 版本：v1.0 | 日期：2026-06-04

---

## 一、总体架构

每个 Agent 拥有独立的 aiohttp HTTP 服务器，监听独立端口，对外提供 OpenAI 兼容 API。
一个 **AgentManager** 统一管理所有 Agent 的生命周期，并在独立管理端口上暴露控制 API。

```
┌─────────────────────────────────────────────────────────┐
│                   AgentManagerService                    │
│                   管理端口: 8640                          │
│                                                         │
│  POST /v1/agents          → 创建 Agent                  │
│  POST /v1/agents/{id}/start → 启动 Agent 服务器          │
│  POST /v1/agents/{id}/stop  → 停止 Agent 服务器          │
│  GET  /v1/agents          → 列出所有 Agent               │
│  ...                                                    │
└─────────────┬───────────────────────────────────────────┘
              │ 创建/管理
    ┌─────────┼──────────────────────────────┐
    ▼         ▼                              ▼
┌──────────┐ ┌──────────┐            ┌──────────┐
│ Agent A  │ │ Agent B  │    ...     │ Agent N  │
│ 端口:8001 │ │ 端口:8002 │            │ 端口:800N │
│          │ │          │            │          │
│ soul:    │ │ soul:     │            │ soul:    │
│ "你是    │ │ "你是     │            │ "你是    │
│  Alice"  │ │  Bob"    │            │  ..."    │
│          │ │          │            │          │
│ AIAgent  │ │ AIAgent  │            │ AIAgent  │
│ (claude) │ │ (gpt-4o) │            │ (...)    │
└──────────┘ └──────────┘            └──────────┘

每个 Agent 独立暴露 OpenAI 兼容 API：
  POST /v1/chat/completions
  POST /v1/responses
  GET  /v1/models
  POST /api/sessions
  POST /api/sessions/{id}/chat[/stream]
```

---

## 二、目录结构

```
hermes-agent/
├── gateway/
│   ├── agent_manager/
│   │   ├── __init__.py          # 公开 AgentManager、AgentConfig
│   │   ├── models.py            # AgentConfig, AgentInstance, AgentStatus
│   │   ├── store.py             # AgentStore (SQLite 持久化)
│   │   ├── adapter.py           # AgentAPIAdapter (APIServerAdapter 子类)
│   │   ├── manager.py           # AgentManager (生命周期编排)
│   │   └── control_server.py    # ControlServer (管理 REST API)
│   └── platforms/
│       └── api_server.py        # 现有文件，无需修改
├── hermes_agent_manager.py      # CLI 入口
└── docs/
    └── agent-manager-design.md  # 本文档
```

---

## 三、数据模型

### 3.1 AgentConfig

```python
# gateway/agent_manager/models.py

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid, time

class AgentStatus(str, Enum):
    STOPPED  = "stopped"   # 已创建，未启动
    STARTING = "starting"  # 正在启动
    RUNNING  = "running"   # 正在运行
    STOPPING = "stopping"  # 正在停止
    ERROR    = "error"     # 启动失败

@dataclass
class AgentConfig:
    # ── 身份 ──────────────────────────────────────────────
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""                    # 可读名称，如 "customer-service"
    description: str = ""             # 简短描述

    # ── 人格 ──────────────────────────────────────────────
    soul: str = ""                    # 系统提示词 / 人格定义 (SOUL.md 内容)

    # ── 网络 ──────────────────────────────────────────────
    port: int = 0                     # 0 = 自动分配空闲端口
    host: str = "127.0.0.1"          # 绑定 IP
    api_key: str = ""                 # Bearer token（空=不鉴权）

    # ── 模型 ──────────────────────────────────────────────
    model: Optional[str] = None       # None = 继承全局 config.yaml
    provider: Optional[str] = None    # None = 继承全局
    base_url: Optional[str] = None    # None = 继承全局

    # ── 能力 ──────────────────────────────────────────────
    tools: List[str] = field(default_factory=list)   # 空=继承全局工具集
    max_iterations: int = 90

    # ── 运行时策略 ────────────────────────────────────────
    auto_start: bool = False          # 管理器启动时自动拉起

    # ── 元数据 ────────────────────────────────────────────
    meta: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class AgentInstance:
    """AgentConfig 的运行时快照，不持久化"""
    config: AgentConfig
    status: AgentStatus = AgentStatus.STOPPED
    actual_port: int = 0             # auto_start 后的实际端口
    error: str = ""                  # 最近错误信息
    started_at: Optional[float] = None
    adapter: Optional[Any] = None    # AgentAPIAdapter 实例引用（运行时持有）
```

---

## 四、持久化层

### 4.1 SQLite 表结构

```python
# gateway/agent_manager/store.py

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS agents (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    soul            TEXT NOT NULL DEFAULT '',
    port            INTEGER NOT NULL DEFAULT 0,
    host            TEXT NOT NULL DEFAULT '127.0.0.1',
    api_key         TEXT NOT NULL DEFAULT '',
    model           TEXT,
    provider        TEXT,
    base_url        TEXT,
    tools           TEXT NOT NULL DEFAULT '[]',   -- JSON array
    max_iterations  INTEGER NOT NULL DEFAULT 90,
    auto_start      INTEGER NOT NULL DEFAULT 0,   -- 0/1 bool
    meta            TEXT NOT NULL DEFAULT '{}',   -- JSON object
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
)
"""
```

### 4.2 AgentStore 接口

```python
class AgentStore:
    def __init__(self, db_path: str): ...

    def create(self, cfg: AgentConfig) -> AgentConfig: ...
    def get(self, agent_id: str) -> Optional[AgentConfig]: ...
    def list_all(self) -> List[AgentConfig]: ...
    def update(self, agent_id: str, patch: Dict[str, Any]) -> AgentConfig: ...
    def delete(self, agent_id: str) -> bool: ...
    def list_auto_start(self) -> List[AgentConfig]: ...   # auto_start=1
```

存储路径：`~/.hermes/agent_manager.db`（可通过 `HERMES_AGENT_MANAGER_DB` 覆盖）

---

## 五、Agent HTTP Server

### 5.1 AgentAPIAdapter（复用现有 APIServerAdapter）

```python
# gateway/agent_manager/adapter.py

from gateway.platforms.api_server import APIServerAdapter
from gateway.config import PlatformConfig
from .models import AgentConfig

class AgentAPIAdapter(APIServerAdapter):
    """
    APIServerAdapter 的子类，将 AgentConfig 注入到 agent 创建流程。
    覆盖三个方法以注入 soul / model / tools。
    """

    def __init__(self, agent_cfg: AgentConfig, gateway_runner):
        platform_cfg = PlatformConfig(
            enabled=True,
            extra={
                "host":    agent_cfg.host,
                "port":    agent_cfg.port,
                "key":     agent_cfg.api_key,
            },
        )
        super().__init__(platform_cfg, gateway_runner)
        self._agent_cfg = agent_cfg

    # ── 覆盖：注入 soul 作为默认系统提示词 ─────────────────
    def _create_agent(
        self,
        ephemeral_system_prompt=None,
        session_id=None,
        stream_delta_callback=None,
        tool_progress_callback=None,
        tool_start_callback=None,
        tool_complete_callback=None,
        gateway_session_key=None,
        model_override=None,
    ):
        return super()._create_agent(
            # 外部传入优先，否则用 soul
            ephemeral_system_prompt=ephemeral_system_prompt or self._agent_cfg.soul or None,
            session_id=session_id,
            stream_delta_callback=stream_delta_callback,
            tool_progress_callback=tool_progress_callback,
            tool_start_callback=tool_start_callback,
            tool_complete_callback=tool_complete_callback,
            gateway_session_key=gateway_session_key,
            # model_override: 外部请求 > AgentConfig.model > 全局 config
            model_override=model_override or self._agent_cfg.model or None,
        )

    # ── 覆盖：工具集注入 ────────────────────────────────────
    def _get_agent_toolsets(self):
        if self._agent_cfg.tools:
            return sorted(self._agent_cfg.tools)
        return super()._get_agent_toolsets()
```

### 5.2 端口自动分配

```python
# gateway/agent_manager/manager.py（片段）

import socket

def _find_free_port(start: int = 8700, end: int = 9000) -> int:
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in [{start}, {end})")
```

---

## 六、AgentManager（生命周期编排）

```python
# gateway/agent_manager/manager.py

class AgentManager:
    def __init__(
        self,
        db_path: str,
        gateway_runner,                 # 全局 GatewayRunner（提供 LLM 凭证等全局配置）
        management_port: int = 8640,
        management_host: str = "127.0.0.1",
        management_api_key: str = "",
    ):
        self._store = AgentStore(db_path)
        self._runner = gateway_runner
        self._instances: Dict[str, AgentInstance] = {}  # id → AgentInstance
        self._lock = asyncio.Lock()
        self._control = ControlServer(self, management_host, management_port, management_api_key)

    # ── CRUD ───────────────────────────────────────────────────
    async def create_agent(self, cfg: AgentConfig) -> AgentConfig:
        """创建 Agent 配置（不启动）"""
        if cfg.port == 0:
            cfg.port = _find_free_port()
        cfg = self._store.create(cfg)
        self._instances[cfg.id] = AgentInstance(config=cfg)
        if cfg.auto_start:
            await self.start_agent(cfg.id)
        return cfg

    async def update_agent(self, agent_id: str, patch: Dict[str, Any]) -> AgentConfig:
        """更新配置（若正在运行则需先停止）"""
        instance = self._instances.get(agent_id)
        if instance and instance.status == AgentStatus.RUNNING:
            raise RuntimeError("Agent is running, stop it first")
        cfg = self._store.update(agent_id, patch)
        self._instances[agent_id].config = cfg
        return cfg

    async def delete_agent(self, agent_id: str) -> None:
        await self.stop_agent(agent_id, ignore_not_running=True)
        self._store.delete(agent_id)
        self._instances.pop(agent_id, None)

    # ── 生命周期 ───────────────────────────────────────────────
    async def start_agent(self, agent_id: str) -> AgentInstance:
        """启动指定 Agent 的 aiohttp 服务器"""
        async with self._lock:
            instance = self._get_instance(agent_id)
            if instance.status == AgentStatus.RUNNING:
                return instance

            instance.status = AgentStatus.STARTING
            try:
                adapter = AgentAPIAdapter(instance.config, self._runner)
                await adapter.connect()                       # 复用现有 connect() 启动 aiohttp
                instance.adapter = adapter
                instance.actual_port = instance.config.port
                instance.status = AgentStatus.RUNNING
                instance.started_at = time.time()
                instance.error = ""
            except Exception as e:
                instance.status = AgentStatus.ERROR
                instance.error = str(e)
                raise
        return instance

    async def stop_agent(self, agent_id: str, ignore_not_running: bool = False) -> None:
        async with self._lock:
            instance = self._instances.get(agent_id)
            if not instance or instance.status != AgentStatus.RUNNING:
                if ignore_not_running:
                    return
                raise RuntimeError(f"Agent {agent_id} is not running")
            instance.status = AgentStatus.STOPPING
            try:
                await instance.adapter.disconnect()           # 复用现有 disconnect() 停止 aiohttp
            finally:
                instance.adapter = None
                instance.status = AgentStatus.STOPPED

    async def restart_agent(self, agent_id: str) -> AgentInstance:
        await self.stop_agent(agent_id, ignore_not_running=True)
        return await self.start_agent(agent_id)

    # ── 查询 ───────────────────────────────────────────────────
    def get_instance(self, agent_id: str) -> AgentInstance:
        instance = self._instances.get(agent_id)
        if not instance:
            raise KeyError(f"Agent {agent_id} not found")
        return instance

    def list_instances(self) -> List[AgentInstance]:
        return list(self._instances.values())

    # ── 初始化（程序启动时）───────────────────────────────────
    async def startup(self):
        """从 DB 加载所有 Agent，并启动 auto_start 的"""
        for cfg in self._store.list_all():
            self._instances[cfg.id] = AgentInstance(config=cfg)
        for cfg in self._store.list_auto_start():
            try:
                await self.start_agent(cfg.id)
            except Exception as e:
                # auto_start 失败不中断管理器启动
                logger.error("Auto-start agent %s failed: %s", cfg.name, e)
        await self._control.start()

    async def shutdown(self):
        """优雅关闭所有运行中的 Agent"""
        await self._control.stop()
        for instance in list(self._instances.values()):
            if instance.status == AgentStatus.RUNNING:
                await self.stop_agent(instance.config.id, ignore_not_running=True)
```

---

## 七、管理 REST API

### 7.1 端点规范

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/agents` | 创建 Agent |
| `GET` | `/v1/agents` | 列出所有 Agent（含状态） |
| `GET` | `/v1/agents/{id}` | 获取单个 Agent 详情 |
| `PATCH` | `/v1/agents/{id}` | 更新 Agent 配置 |
| `DELETE` | `/v1/agents/{id}` | 删除 Agent |
| `POST` | `/v1/agents/{id}/start` | 启动 Agent 服务器 |
| `POST` | `/v1/agents/{id}/stop` | 停止 Agent 服务器 |
| `POST` | `/v1/agents/{id}/restart` | 重启 Agent 服务器 |
| `GET` | `/v1/agents/{id}/status` | 获取运行时状态 |
| `GET` | `/v1/health` | 管理器健康检查 |

### 7.2 请求/响应示例

**创建 Agent**
```http
POST /v1/agents
Content-Type: application/json
Authorization: Bearer <management_api_key>

{
  "name": "customer-service",
  "description": "客服机器人",
  "soul": "你是 Hermes 客服助手，友好、专业，专注于解决用户问题。回复用中文。",
  "port": 8701,
  "host": "0.0.0.0",
  "api_key": "secret-token-abc",
  "model": "claude-opus-4-8",
  "tools": ["web_search", "file_read"],
  "max_iterations": 30,
  "auto_start": true,
  "meta": {
    "team": "support",
    "env": "production"
  }
}
```

**响应**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "customer-service",
  "description": "客服机器人",
  "soul": "你是 Hermes 客服助手...",
  "port": 8701,
  "host": "0.0.0.0",
  "api_key": "secret-token-abc",
  "model": "claude-opus-4-8",
  "tools": ["web_search", "file_read"],
  "max_iterations": 30,
  "auto_start": true,
  "status": "running",
  "actual_port": 8701,
  "started_at": 1748995200.0,
  "meta": {"team": "support", "env": "production"},
  "created_at": 1748995200.0,
  "updated_at": 1748995200.0
}
```

**列出所有 Agent（含运行时状态）**
```http
GET /v1/agents
```
```json
{
  "agents": [
    {
      "id": "550e8400-...",
      "name": "customer-service",
      "port": 8701,
      "status": "running",
      "actual_port": 8701,
      "model": "claude-opus-4-8"
    },
    {
      "id": "6ba7b810-...",
      "name": "code-reviewer",
      "port": 8702,
      "status": "stopped",
      "model": null
    }
  ],
  "total": 2,
  "running": 1
}
```

**PATCH 更新（仅更新 soul）**
```http
PATCH /v1/agents/550e8400-...
Content-Type: application/json

{
  "soul": "你是更新后的客服助手..."
}
```
> 注意：Agent 运行时不允许更新，需先 stop。

**启动/停止**
```http
POST /v1/agents/550e8400-.../start   → {"status": "running", "actual_port": 8701}
POST /v1/agents/550e8400-.../stop    → {"status": "stopped"}
POST /v1/agents/550e8400-.../restart → {"status": "running", "actual_port": 8701}
```

---

## 八、各 Agent 对外 API（每个端口）

每个 Agent 的端口直接复用 `APIServerAdapter` 的全部路由：

```
POST  /v1/chat/completions         OpenAI Chat Completions
POST  /v1/responses                OpenAI Responses API  
GET   /v1/models                   列出模型
GET   /v1/capabilities             能力列表
POST  /api/sessions                创建会话
GET   /api/sessions                列出会话
GET   /api/sessions/{id}           获取会话
POST  /api/sessions/{id}/chat      聊天（同步）
POST  /api/sessions/{id}/chat/stream  聊天（SSE 流式）
POST  /api/sessions/{id}/fork      分叉会话
POST  /v1/runs                     启动异步运行
GET   /v1/runs/{run_id}            获取运行状态
GET   /v1/runs/{run_id}/events     运行事件流（SSE）
```

**调用示例**（向 Agent "customer-service" 发送消息）：
```bash
curl http://localhost:8701/v1/chat/completions \
  -H "Authorization: Bearer secret-token-abc" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-opus-4-8",
    "messages": [{"role": "user", "content": "你好，我的订单在哪里？"}],
    "stream": true
  }'
```

---

## 九、配置文件格式

`~/.hermes/config.yaml` 中新增 `agent_manager` 块：

```yaml
# 现有配置...
model:
  default: claude-opus-4-8

platforms:
  api_server:
    enabled: true

# 新增：Agent Manager 配置
agent_manager:
  enabled: true
  host: "127.0.0.1"
  port: 8640             # 管理端口
  api_key: ""            # 管理 API 鉴权密钥（空=不鉴权）
  db_path: ""            # 空=使用默认 ~/.hermes/agent_manager.db

  # 可选：预定义 Agents（声明式，等同于 POST /v1/agents）
  agents:
    - name: customer-service
      soul: "你是友好的客服助手，用中文回复。"
      port: 8701
      model: claude-opus-4-8
      tools: [web_search]
      auto_start: true

    - name: code-reviewer
      soul: "你是严格的代码审查员，专注于安全性和性能。"
      port: 8702
      tools: [file_read, file_write, run_command]
      auto_start: false
```

---

## 十、CLI 入口

```bash
# 启动 AgentManager（含管理 API + auto_start agents）
hermes-agent-manager

# 等价于：
hermes gateway --agent-manager

# 或通过环境变量
HERMES_AGENT_MANAGER_ENABLED=true hermes gateway
```

`hermes_agent_manager.py`：

```python
#!/usr/bin/env python3
"""
独立的 Agent Manager 启动入口。

用法：
    python hermes_agent_manager.py
    python hermes_agent_manager.py --port 8640 --db ~/.hermes/agents.db
"""
import asyncio, argparse
from gateway.config import load_gateway_config
from gateway.run import GatewayRunner
from gateway.agent_manager import AgentManager
from hermes_constants import get_hermes_home

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8640)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--db", default=str(get_hermes_home() / "agent_manager.db"))
    args = parser.parse_args()

    async def run():
        gw_config = load_gateway_config()
        runner = GatewayRunner(gw_config)
        manager = AgentManager(
            db_path=args.db,
            gateway_runner=runner,
            management_port=args.port,
            management_host=args.host,
            management_api_key=args.api_key,
        )
        await manager.startup()
        try:
            await asyncio.Event().wait()   # 永久阻塞
        except (KeyboardInterrupt, asyncio.CancelledError):
            await manager.shutdown()

    asyncio.run(run())

if __name__ == "__main__":
    main()
```

---

## 十一、实现步骤

### Phase 1：数据层（无外部依赖，可独立测试）
1. 创建 `gateway/agent_manager/models.py` — `AgentConfig`、`AgentInstance`、`AgentStatus`
2. 创建 `gateway/agent_manager/store.py` — `AgentStore` SQLite 实现
3. 编写单元测试 `tests/agent_manager/test_store.py`

### Phase 2：Adapter 集成
4. 创建 `gateway/agent_manager/adapter.py` — `AgentAPIAdapter` 子类
5. 验证：单独实例化 `AgentAPIAdapter`，测试端口绑定和 `/v1/models` 路由
6. 验证：soul 注入到 `_create_agent()` 的 `ephemeral_system_prompt`

### Phase 3：Manager 编排
7. 创建 `gateway/agent_manager/manager.py` — `AgentManager` 完整实现
8. 测试：创建 2 个 Agent，各自启动在不同端口，curl 验证
9. 测试：停止、重启、删除生命周期

### Phase 4：管理 API
10. 创建 `gateway/agent_manager/control_server.py` — `ControlServer` aiohttp 实现
11. 实现全部 REST 端点（CRUD + start/stop/restart/status）
12. 接入 Bearer token 鉴权中间件（复用 `api_server.py` 的 `_auth_middleware`）

### Phase 5：配置与入口
13. 修改 `gateway/config.py` — 新增 `AgentManagerConfig` dataclass 和 `load_gateway_config()` 中的解析
14. 创建 `hermes_agent_manager.py` CLI 入口
15. 集成测试：从 config.yaml 声明式启动多个 Agent

---

## 十二、关键复用点

| 需求 | 复用的现有代码 | 文件 |
|------|--------------|------|
| HTTP 服务器生命周期 | `APIServerAdapter.connect()` / `disconnect()` | `gateway/platforms/api_server.py` |
| OpenAI API 路由 | `APIServerAdapter._setup_routes()` | 同上 |
| Agent 实例化 | `APIServerAdapter._create_agent()` | 同上 |
| LLM 凭证解析 | `GatewayRunner._resolve_runtime_agent_kwargs()` | `gateway/run.py` |
| Bearer 鉴权 | `APIServerAdapter._auth_middleware()` | `gateway/platforms/api_server.py` |
| SSE 流式响应 | `APIServerAdapter._stream_*` 方法族 | 同上 |
| SOUL 文件格式 | `load_soul_md()` — soul 字段即 SOUL.md 内容 | `agent/prompt_builder.py` |
| 会话持久化 | `SessionDB` | `hermes_state.py` |
| 端口/Host 配置 | `PlatformConfig.extra` 字典 | `gateway/config.py` |

---

## 十三、安全考量

| 风险 | 缓解措施 |
|------|---------|
| 管理 API 未鉴权 | `management_api_key` 必填，Bearer token 鉴权 |
| Agent SOUL 注入攻击 | 复用现有 `_scan_context_content()` 扫描威胁模式 |
| 端口冲突 | `_find_free_port()` + 启动前 bind 验证 |
| Agent 间数据泄漏 | 每个 Agent 独立 `session_id` 命名空间 (`agent:{id}:{session}`) |
| soul 内容超长 | 复用现有 `_truncate_content()` 限制 20,000 字符 |

---

## 十四、扩展预留

| 扩展点 | 预留方式 |
|--------|---------|
| Agent 指标监控 | `AgentInstance.meta` + `/v1/agents/{id}/metrics` 端点 |
| 多租户隔离 | `AgentConfig.meta["tenant_id"]` + 管理 API 过滤 |
| Agent 模板 | `POST /v1/agent-templates` + 从模板创建 |
| 热更新 soul | `PATCH /v1/agents/{id}` + `restart` = 滚动更新 |
| Webhook 通知 | `AgentConfig.meta["webhook_url"]` 在状态变更时回调 |
| 水平扩展 | 同一 Agent 多实例 + 负载均衡（下一版本） |
