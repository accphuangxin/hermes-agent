# Multi-Profile API Server — 设计文档

## 背景

当前 `api_server` 平台只服务单个 hermes 实例（单 profile）。本文档描述在 `api_server` 中增加多 profile 管理能力，允许通过 API 创建、启动、停止、路由多个完全隔离的 hermes agent 实例。

## 目标

- 通过 REST API 管理 profile 生命周期（CRUD + 启停）
- 通过单一入口端口代理路由到各 profile 的 gateway
- 与现有 `hermes_cli/profiles.py` 基础设施完全复用，不重复造轮子

## 现有基础

`hermes_cli/profiles.py` 已提供：

| 函数 | 作用 |
|------|------|
| `list_profiles()` | 列出所有 profile，返回 `List[ProfileInfo]` |
| `create_profile(name, clone_from, description)` | 创建 profile，支持从现有 profile 克隆 |
| `delete_profile(name)` | 删除 profile 目录 |
| `profile_exists(name)` | 检查是否存在 |
| `get_profile_dir(name)` | 返回 profile 的 HERMES_HOME 路径 |
| `read_profile_meta(dir)` | 读取 profile.yaml 元数据 |
| `write_profile_meta(dir, ...)` | 写入元数据（description 等） |
| `_check_gateway_running(dir)` | 检查 gateway 进程是否在运行 |
| `ProfileInfo` | 包含 name/path/gateway_running/model/provider/description |

## API 设计

### 层一：Profile CRUD

```
GET    /api/profiles                    列出所有 profile
POST   /api/profiles                    创建 profile
GET    /api/profiles/{name}             查看单个 profile 详情
PATCH  /api/profiles/{name}             更新 profile 元数据（description 等）
DELETE /api/profiles/{name}             删除 profile
```

**POST /api/profiles 请求体：**
```json
{
  "name": "sales",
  "description": "销售助手，使用 qwen3_6 模型",
  "clone_from": "default",        // 可选，从哪个 profile 克隆配置
  "config": {                     // 可选，直接指定初始配置
    "model": "qwen3_6",
    "provider": "custom",
    "base_url": "http://token.cloudci.com/v1",
    "api_key": "sk-xxx"
  }
}
```

**GET /api/profiles 响应：**
```json
{
  "profiles": [
    {
      "name": "default",
      "path": "/Users/a111/.hermes",
      "is_default": true,
      "gateway_running": true,
      "gateway_port": 8643,
      "model": "qwen3_6",
      "provider": "custom",
      "description": ""
    },
    {
      "name": "sales",
      "path": "/Users/a111/.hermes/profiles/sales",
      "is_default": false,
      "gateway_running": false,
      "gateway_port": 8644,
      "model": "claude-sonnet-4-6",
      "provider": "anthropic",
      "description": "销售助手"
    }
  ]
}
```

### 层二：Gateway 启停

```
POST   /api/profiles/{name}/start       启动该 profile 的 gateway
POST   /api/profiles/{name}/stop        停止该 profile 的 gateway
GET    /api/profiles/{name}/status      查询运行状态
```

**POST /api/profiles/{name}/start 响应：**
```json
{
  "name": "sales",
  "status": "starting",
  "port": 8644,
  "pid": 12345,
  "log": "/Users/a111/.hermes/profiles/sales/logs/gateway.log"
}
```

**GET /api/profiles/{name}/status 响应：**
```json
{
  "name": "sales",
  "running": true,
  "pid": 12345,
  "port": 8644,
  "uptime_seconds": 3600,
  "last_exit_code": null
}
```

### 层三：统一请求路由

通过 `X-Hermes-Profile` header 将请求代理到指定 profile 的 gateway：

```
POST /v1/chat/completions
X-Hermes-Profile: sales
→ 透明代理到 http://localhost:8644/v1/chat/completions
```

支持的代理路径（全部透传）：
```
/v1/chat/completions
/v1/chat/completions/stream
/v1/responses
/v1/responses/{id}
/v1/runs
/v1/runs/{id}
/v1/runs/{id}/events      （SSE 流式）
/api/sessions
/api/sessions/{id}/chat
/api/sessions/{id}/chat/stream  （SSE 流式）
```

无 `X-Hermes-Profile` header 时，路由到默认 profile（当前行为，完全向后兼容）。

## 端口分配

每个 profile 需要独立端口，分配策略：

**优先读取配置（推荐）**：在各 profile 的 `config.yaml` 中显式配置：
```yaml
gateway:
  platforms:
    api_server:
      extra:
        port: 8644
```

**自动分配（回退）**：从 `~/.hermes/profile_ports.json` 读取持久化的端口映射，首次启动时从 `8644` 开始递增分配，避免冲突。

```json
{
  "default": 8643,
  "sales": 8644,
  "support": 8645
}
```

## 实现结构

### 新增文件

```
gateway/
  profile_manager.py      # 子进程管理、端口分配、状态跟踪
```

### 修改文件

```
gateway/platforms/api_server.py   # 新增 /api/profiles/* 路由 + 代理中间件
```

### profile_manager.py 核心类

```python
class ProfileManager:
    """管理多个 profile gateway 子进程。"""

    def __init__(self):
        self._processes: dict[str, subprocess.Popen] = {}
        self._ports: dict[str, int] = {}      # 从 profile_ports.json 加载

    def start(self, name: str) -> int:
        """启动 profile gateway，返回端口号。"""
        port = self._get_or_assign_port(name)
        profile_dir = get_profile_dir(name)
        env = {**os.environ, "HERMES_HOME": str(profile_dir)}
        proc = subprocess.Popen(
            [sys.executable, "-m", "hermes_cli.main", "gateway", "run", "--replace"],
            env=env,
            stdout=open(profile_dir / "logs/gateway.log", "a"),
            stderr=subprocess.STDOUT,
        )
        self._processes[name] = proc
        return port

    def stop(self, name: str) -> None:
        """停止 profile gateway。"""
        proc = self._processes.pop(name, None)
        if proc and proc.poll() is None:
            proc.terminate()

    def status(self, name: str) -> dict:
        proc = self._processes.get(name)
        running = proc is not None and proc.poll() is None
        return {"running": running, "port": self._ports.get(name), "pid": proc.pid if running else None}

    def proxy_url(self, name: str) -> str | None:
        port = self._ports.get(name)
        return f"http://127.0.0.1:{port}" if port else None
```

### api_server.py 路由层新增

```python
# Profile 管理路由
router.add_get("/api/profiles", handle_list_profiles)
router.add_post("/api/profiles", handle_create_profile)
router.add_get("/api/profiles/{name}", handle_get_profile)
router.add_patch("/api/profiles/{name}", handle_update_profile)
router.add_delete("/api/profiles/{name}", handle_delete_profile)
router.add_post("/api/profiles/{name}/start", handle_start_profile)
router.add_post("/api/profiles/{name}/stop", handle_stop_profile)
router.add_get("/api/profiles/{name}/status", handle_profile_status)

# 代理中间件（在现有路由前插入）
@middleware
async def profile_proxy_middleware(request, handler):
    profile_name = request.headers.get("X-Hermes-Profile")
    if profile_name:
        target = profile_manager.proxy_url(profile_name)
        if not target:
            return web.json_response({"error": f"Profile '{profile_name}' not running"}, status=503)
        return await _proxy_request(request, target)
    return await handler(request)
```

### SSE 流式代理

SSE (`/v1/runs/{id}/events`, `/api/sessions/{id}/chat/stream`) 需要特殊处理，不能缓冲响应：

```python
async def _proxy_request(request, target_base):
    url = target_base + request.path_qs
    async with aiohttp.ClientSession() as session:
        async with session.request(
            request.method, url,
            headers=_forward_headers(request),
            data=await request.read(),
        ) as resp:
            if resp.content_type == "text/event-stream":
                # SSE: 逐块透传，不缓冲
                response = web.StreamResponse(status=resp.status, headers=resp.headers)
                await response.prepare(request)
                async for chunk in resp.content.iter_any():
                    await response.write(chunk)
                return response
            else:
                body = await resp.read()
                return web.Response(status=resp.status, body=body, headers=resp.headers)
```

## 实现顺序

```
阶段 1（1天）  profile_manager.py 骨架 + /api/profiles CRUD
阶段 2（1天）  start/stop/status + 端口分配 + 子进程管理
阶段 3（1.5天）proxy 中间件 + SSE 透传
阶段 4（0.5天）测试 + 错误处理（profile 不存在/端口冲突/进程 crash）
```

## 风险点

| 风险 | 缓解措施 |
|------|----------|
| 端口冲突 | 启动前 `socket.bind` 探测端口可用性 |
| 子进程 crash 后请求失败 | status 接口返回 503，proxy 中间件检测进程存活 |
| profile 删除时 gateway 仍在运行 | DELETE 前自动调用 stop |
| Windows 子进程信号处理差异 | Windows 用 `proc.terminate()` 而非 SIGTERM |
| 大量 profile 同时运行内存压力 | 文档建议 + status 接口暴露内存指标 |

## 向后兼容

- 无 `X-Hermes-Profile` header 时行为与现在完全一致
- 所有现有 `/v1/*` 和 `/api/*` 路由不变
- `api_server` 配置不需要变化
