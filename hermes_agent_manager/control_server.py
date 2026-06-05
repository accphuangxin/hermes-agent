from __future__ import annotations

"""
ControlServer — management REST API for AgentManager.

Runs on a dedicated port (default 8640) as a fully independent
aiohttp instance, completely separate from the per-agent servers.
"""

import hashlib
import hmac
import json
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from aiohttp import web
    _AIOHTTP_OK = True
except ImportError:
    _AIOHTTP_OK = False

if TYPE_CHECKING:
    from .manager import AgentManager


def _real_hermes_home():
    """返回用户真实的 ~/.hermes 路径，忽略 HERMES_HOME 环境变量。

    pkg 安装的 launcher 脚本将 HERMES_HOME 设为 /usr/local/hermes（安装目录），
    导致 get_hermes_home() 返回错误路径。这里直接用 Path.home() / '.hermes'。
    """
    from pathlib import Path as _P
    return _P.home() / ".hermes"


def _profile_gateway_running(profile_path, port: int = 0) -> bool:
    """优先通过 HTTP /v1/health 探测 gateway 是否在线，PID 文件作为兜底。"""
    # 方法1：HTTP 探测（最准确，不受 PID 文件残留影响）
    if port:
        try:
            import urllib.request
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/v1/health",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=1) as resp:
                return resp.status == 200
        except Exception:
            pass

    # 方法2：PID 文件兜底
    import os
    from pathlib import Path as _P
    pid_file = _P(profile_path) / "gateway.pid"
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _read_profile_full_config(profile_path) -> dict:
    """从 profile 目录的 config.yaml 直接读取所有需要的字段。"""
    try:
        import yaml
        from pathlib import Path as _P
        cfg_file = _P(profile_path) / "config.yaml"
        if not cfg_file.exists():
            return {}
        cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}

        # model / provider
        model_block = cfg.get("model", {})
        model    = model_block.get("default") or model_block.get("model") or ""
        provider = model_block.get("provider", "")

        # api_server port / key
        api_cfg = cfg.get("platforms", {}).get("api_server", {})
        extra   = api_cfg.get("extra", {})
        port    = extra.get("port") or api_cfg.get("port")
        key     = extra.get("key")  or api_cfg.get("key") or ""

        # skill count — 统计 skills/ 目录下的 SKILL.md 文件数
        skills_dir = _P(profile_path) / "skills"
        skill_count = len(list(skills_dir.glob("*/SKILL.md"))) if skills_dir.is_dir() else 0

        # description — 从 profile.yaml 读取
        description = ""
        profile_yaml = _P(profile_path) / "profile.yaml"
        if profile_yaml.exists():
            pmeta = yaml.safe_load(profile_yaml.read_text(encoding="utf-8")) or {}
            description = pmeta.get("description", "")

        return {
            "model":       model,
            "provider":    provider,
            "port":        int(port) if port else 0,
            "key":         str(key) if key else "",
            "skill_count": skill_count,
            "description": description,
        }
    except Exception:
        return {}


def _list_hermes_profile_agents() -> list:
    """读取 hermes 所有 profile，返回与 managed agent 格式兼容的列表。

    完全基于文件系统直接读取，不调用 list_profiles()，
    避免受 HERMES_HOME=/usr/local/hermes 干扰。
    """
    try:
        real_hermes = _real_hermes_home()

        raw_profiles = []
        # default profile（根目录）
        if (real_hermes / "config.yaml").exists():
            raw_profiles.append({
                "name": "default",
                "path": real_hermes,
                "is_default": True,
            })
        # 其他 profiles
        profiles_dir = real_hermes / "profiles"
        if profiles_dir.is_dir():
            for d in sorted(profiles_dir.iterdir()):
                if d.is_dir() and (d / "config.yaml").exists():
                    raw_profiles.append({
                        "name": d.name,
                        "path": d,
                        "is_default": False,
                    })
    except Exception:
        return []

    result = []
    for rp in raw_profiles:
        info       = _read_profile_full_config(rp["path"])
        gw_running = _profile_gateway_running(rp["path"], port=info.get("port", 0))
        result.append(_profile_to_dict(rp["name"], rp["path"], info, gw_running))
    return result


def _restart_profile_gateway(profile_name: str) -> None:
    """重启指定 profile 的 gateway 服务（后台执行，不阻塞）。"""
    import os, subprocess
    real_home = _real_hermes_home()
    profile_home = str(real_home) if profile_name == "default" else str(real_home / "profiles" / profile_name)

    hermes_bin = subprocess.run(
        ["which", "hermes"], capture_output=True, text=True
    ).stdout.strip() or "hermes"

    env = os.environ.copy()
    env["HERMES_HOME"] = profile_home

    # 后台启动，不等待，避免阻塞事件循环（gateway restart 需要等旧进程退出）
    subprocess.Popen(
        [hermes_bin, "gateway", "restart"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    logger.info("Gateway restart triggered for profile %r (background)", profile_name)


def _install_and_start_gateway(profile_name: str) -> None:
    """为指定 profile 安装 launchd/systemd 服务并启动 gateway。

    等价于：hermes -p {profile_name} gateway install && start
    通过设置 HERMES_HOME 切换 profile 上下文后调用现有 gateway 函数。
    """
    import os, platform, subprocess, sys
    real_home = _real_hermes_home()

    # 计算该 profile 的 HERMES_HOME
    if profile_name == "default":
        profile_home = str(real_home)
    else:
        profile_home = str(real_home / "profiles" / profile_name)

    # 用子进程执行，完全隔离环境变量，避免污染当前进程
    hermes_bin = subprocess.run(
        ["which", "hermes"], capture_output=True, text=True
    ).stdout.strip() or "hermes"

    env = os.environ.copy()
    env["HERMES_HOME"] = profile_home

    # install 注册服务（launchd/systemd），后台 start 确保立即启动
    result = subprocess.run(
        [hermes_bin, "gateway", "install"],
        env=env, capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        logger.warning(
            "gateway install for %r exited %d: %s",
            profile_name, result.returncode,
            result.stderr.strip() or result.stdout.strip(),
        )
    else:
        logger.info("Gateway installed for profile %r", profile_name)

    # install 完成后显式触发 start（后台，不阻塞）
    subprocess.Popen(
        [hermes_bin, "gateway", "start"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    logger.info("Gateway start triggered for profile %r (background)", profile_name)


def _patch_profile_api_server(profile_dir, port=None, key=None) -> None:
    """将 api_server 配置写入 profile 的 config.yaml。

    始终写入 enabled=true、extra 结构。
    port/key 为 None 时只做结构初始化，不覆盖已有值。
    """
    try:
        from pathlib import Path as _P
        from ruamel.yaml import YAML
        cfg_file = _P(profile_dir) / "config.yaml"
        ry = YAML()
        ry.preserve_quotes = True
        ry.width = 4096  # 避免长字符串被折行
        with open(cfg_file, encoding="utf-8") as f:
            cfg = ry.load(f) or {}

        # 确保 platforms.api_server.extra 结构存在
        if "platforms" not in cfg:
            cfg["platforms"] = {}
        if "api_server" not in cfg["platforms"]:
            cfg["platforms"]["api_server"] = {}
        api_cfg = cfg["platforms"]["api_server"]
        if "extra" not in api_cfg:
            api_cfg["extra"] = {}

        api_cfg["enabled"] = True

        # 写入 extra 块
        if port is not None:
            api_cfg["extra"]["port"] = int(port)
            # 删除顶层同名字段，避免与 extra 中的值冲突
            api_cfg.pop("port", None)
        if key is not None:
            api_cfg["extra"]["key"] = str(key)
            # 删除顶层旧 key（克隆时从 default 带过来的），以 extra.key 为准
            api_cfg.pop("key", None)
            # 删除 extra 中遗留的 api_key（克隆时从旧配置带过来）
            api_cfg["extra"].pop("api_key", None)
        # 保留 cors_origins（如果已有则不覆盖）
        if "cors_origins" not in api_cfg["extra"]:
            api_cfg["extra"]["cors_origins"] = "*"
        # 顶层 cors_origins 也统一移到 extra 下
        if "cors_origins" in api_cfg and "cors_origins" in api_cfg["extra"]:
            api_cfg.pop("cors_origins", None)

        with open(cfg_file, "w", encoding="utf-8") as f:
            ry.dump(cfg, f)

        logger.debug(
            "Patched api_server config: port=%s key=%s dir=%s",
            port, "***" if key else None, profile_dir,
        )
    except Exception as e:
        logger.warning("Failed to patch api_server config: %s", e)


def _patch_profile_description(profile_dir, description: str) -> None:
    """将 description 写入 profile.yaml。"""
    try:
        from pathlib import Path as _P
        from ruamel.yaml import YAML
        profile_file = _P(profile_dir) / "profile.yaml"
        ry = YAML()
        ry.preserve_quotes = True
        ry.width = 4096
        cfg = {}
        if profile_file.exists():
            with open(profile_file, encoding="utf-8") as f:
                cfg = ry.load(f) or {}
        cfg["description"] = description
        cfg["description_auto"] = False
        with open(profile_file, "w", encoding="utf-8") as f:
            ry.dump(cfg, f)
    except Exception as e:
        logger.warning("Failed to patch profile description: %s", e)


def _patch_profile_model(profile_dir, model=None, provider=None) -> None:
    """将 model/provider 写入 config.yaml 的 model 块。"""
    try:
        from pathlib import Path as _P
        from ruamel.yaml import YAML
        cfg_file = _P(profile_dir) / "config.yaml"
        ry = YAML()
        ry.preserve_quotes = True
        ry.width = 4096
        with open(cfg_file, encoding="utf-8") as f:
            cfg = ry.load(f) or {}
        if "model" not in cfg:
            cfg["model"] = {}
        if model is not None:
            cfg["model"]["default"] = str(model)
        if provider is not None:
            cfg["model"]["provider"] = str(provider)
        with open(cfg_file, "w", encoding="utf-8") as f:
            ry.dump(cfg, f)
    except Exception as e:
        logger.warning("Failed to patch profile model: %s", e)


def _profile_to_dict(name: str, profile_dir, info: dict, gw_running: bool) -> dict:
    """把 profile 信息转换为 API 响应格式。"""
    from pathlib import Path as _P
    port = info.get("port", 0)
    return {
        "id":             f"hermes-profile-{name}",
        "object":         "agent",
        "name":           name,
        "isDefault":      name == "default",
        "model":          info.get("model", ""),
        "provider":       info.get("provider", ""),
        "gatewayRunning": gw_running,
        "skillCount":     info.get("skill_count", 0),
        "description":    info.get("description", ""),
        "apiServerPort":  port,
        "apiServerKey":   info.get("key", ""),
        "source":         "hermes-profile",
        "status":         "running" if gw_running else "stopped",
        "actual_port":    port,
        "soul":           _P(profile_dir / "SOUL.md").read_text(encoding="utf-8").strip()
                          if (_P(profile_dir) / "SOUL.md").exists() else "",
        "meta":           {},
    }


def _json_response(data: Any, status: int = 200) -> "web.Response":
    return web.Response(
        text=json.dumps(data, ensure_ascii=False),
        status=status,
        content_type="application/json",
    )


def _error(message: str, status: int = 400) -> "web.Response":
    return _json_response({"error": message}, status=status)


class ControlServer:
    """Thin aiohttp server that exposes CRUD + lifecycle endpoints for AgentManager."""

    def __init__(
        self,
        manager: "AgentManager",
        host: str = "127.0.0.1",
        port: int = 8640,
        api_key: str = "",
    ) -> None:
        self._manager = manager
        self.host     = host
        self.port     = port
        self._api_key = api_key
        self._app: Optional["web.Application"] = None
        self._runner = None
        self._site   = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if not _AIOHTTP_OK:
            logger.error("aiohttp is not installed; ControlServer cannot start")
            return

        self._app = web.Application(middlewares=[self._auth_middleware])
        self._register_routes()
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        logger.info("ControlServer listening on http://%s:%d", self.host, self.port)

    async def stop(self) -> None:
        if self._site:
            await self._site.stop()
            self._site = None
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        self._app = None
        logger.info("ControlServer stopped")

    # ------------------------------------------------------------------
    # Auth middleware
    # ------------------------------------------------------------------

    @web.middleware
    async def _auth_middleware(self, request: "web.Request", handler):
        # Skip auth for health check and when no key is configured
        if request.path == "/v1/health" or not self._api_key:
            return await handler(request)

        auth = request.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        expected = self._api_key.encode()
        provided = token.encode()
        if not hmac.compare_digest(
            hashlib.sha256(expected).digest(),
            hashlib.sha256(provided).digest(),
        ):
            return _error("Unauthorized", status=401)
        return await handler(request)

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    def _register_routes(self) -> None:
        r = self._app.router
        r.add_get ("/v1/health",                self._handle_health)
        r.add_post("/v1/agents",                self._handle_create)
        r.add_get ("/v1/agents",                self._handle_list)
        r.add_get ("/v1/agents/{id}",           self._handle_get)
        r.add_patch("/v1/agents/{id}",          self._handle_update)
        r.add_delete("/v1/agents/{id}",         self._handle_delete)
        r.add_post("/v1/agents/{id}/start",     self._handle_start)
        r.add_post("/v1/agents/{id}/stop",      self._handle_stop)
        r.add_post("/v1/agents/{id}/restart",   self._handle_restart)
        r.add_get ("/v1/agents/{id}/status",    self._handle_status)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_health(self, request: "web.Request") -> "web.Response":
        running = sum(
            1 for i in self._manager.list_instances()
            if i.status.value == "running"
        )
        return _json_response({
            "status":  "ok",
            "agents":  len(self._manager.list_instances()),
            "running": running,
            "time":    time.time(),
        })

    async def _handle_create(self, request: "web.Request") -> "web.Response":
        """
        创建 Agent = 调用 hermes profile create，在 ~/.hermes/profiles/{name} 下
        建立完整的 profile 目录结构。

        请求体字段：
          name        必填，profile 名称
          clone       bool，是否从当前 default profile 克隆配置（推荐 true）
          clone_from  string，指定克隆来源 profile，默认从 default 克隆
          soul        string，写入 profile 的 SOUL.md（可选）
          description string，profile 描述（可选）
          api_server_port  int，写入 config.yaml 的 api_server 端口（可选）
          api_server_key   string，写入 config.yaml 的 api_server key（可选）
        """
        try:
            body: Dict[str, Any] = await request.json()
        except Exception:
            return _error("Invalid JSON body")

        name = (body.get("name") or "").strip()
        if not name:
            return _error("'name' is required")

        clone       = bool(body.get("clone", True))
        clone_from  = body.get("clone_from") or None
        soul        = (body.get("soul") or "").strip()
        description = (body.get("description") or "").strip()
        api_port    = body.get("api_server_port") or body.get("port")
        api_key     = (body.get("api_server_key") or body.get("api_key") or "").strip()

        try:
            import asyncio, os
            loop = asyncio.get_event_loop()

            # 修正 HERMES_HOME，确保 profile 创建在 ~/.hermes 而非安装目录
            real_home = str(_real_hermes_home())
            os.environ["HERMES_HOME"] = real_home

            # 1. 创建 profile 目录（在线程池里跑，避免阻塞事件循环）
            from hermes_cli.profiles import create_profile, create_wrapper_script
            profile_dir = await loop.run_in_executor(
                None,
                lambda: create_profile(
                    name=name,
                    clone_from=clone_from,
                    clone_config=clone,
                    description=description or None,
                ),
            )

            # 2. 删除克隆带来的 .env（不应继承父 profile 的密钥）
            env_file = profile_dir / ".env"
            if env_file.exists():
                env_file.unlink()

            # 3. 覆盖写入 SOUL.md（如果传了 soul）
            if soul:
                (profile_dir / "SOUL.md").write_text(soul, encoding="utf-8")

            # 4. 写入 api_server 端口/key 到 config.yaml
            # 无论是否传了端口，都确保 api_server.enabled=true 已写入
            # api_port=0 / None 时跳过端口写入（保留克隆来的值或不设置）
            _patch_profile_api_server(
                profile_dir,
                port=int(api_port) if api_port else None,
                key=api_key or None,
            )

            # 5. 创建别名 wrapper script（~/.local/bin/{name} → hermes -p {name}）
            await loop.run_in_executor(
                None,
                lambda: create_wrapper_script(name),
            )

            # 6. 安装并启动 gateway 服务
            await loop.run_in_executor(
                None,
                lambda: _install_and_start_gateway(name),
            )

        except FileExistsError as exc:
            return _error(str(exc), status=409)
        except (ValueError, FileNotFoundError) as exc:
            return _error(str(exc))
        except Exception as exc:
            logger.exception("create profile failed")
            return _error(str(exc), status=500)

        # 6. 返回新 profile 的完整信息
        info = _read_profile_full_config(profile_dir)
        gw_running = _profile_gateway_running(profile_dir, port=info.get("port", 0))
        return _json_response(_profile_to_dict(name, profile_dir, info, gw_running), status=201)

    async def _handle_list(self, request: "web.Request") -> "web.Response":
        # manager 自己管理的 Agent
        managed = [i.to_dict() for i in self._manager.list_instances()]

        # hermes 原生 profiles（每个 profile = 一个独立 gateway Agent）
        hermes_agents = _list_hermes_profile_agents()

        # 合并：managed 优先，profile 中与 managed 同名的不重复展示
        managed_names = {a["name"] for a in managed}
        merged = managed + [a for a in hermes_agents if a["name"] not in managed_names]

        running = sum(1 for a in merged if a.get("status") == "running")
        return _json_response({
            "agents":  merged,
            "total":   len(merged),
            "running": running,
        })

    async def _handle_get(self, request: "web.Request") -> "web.Response":
        agent_id = request.match_info["id"]
        try:
            instance = self._manager.get_instance(agent_id)
        except KeyError:
            return _error(f"Agent {agent_id!r} not found", status=404)
        return _json_response(instance.to_dict())

    async def _handle_update(self, request: "web.Request") -> "web.Response":
        agent_id = request.match_info["id"]
        try:
            body = await request.json()
        except Exception:
            return _error("Invalid JSON body")

        # hermes profile agent
        if agent_id.startswith("hermes-profile-"):
            return await self._update_profile_agent(agent_id, body)

        try:
            cfg = await self._manager.update_agent(agent_id, body)
        except KeyError:
            return _error(f"Agent {agent_id!r} not found", status=404)
        except RuntimeError as exc:
            return _error(str(exc), status=409)

        instance = self._manager.get_instance(cfg.id)
        return _json_response(instance.to_dict())

    async def _update_profile_agent(self, agent_id: str, body: dict) -> "web.Response":
        """更新 hermes profile agent 的配置字段。

        支持字段：
          soul             → SOUL.md
          description      → profile.yaml
          api_server_port  → config.yaml platforms.api_server.extra.port
          api_server_key   → config.yaml platforms.api_server.extra.key
          model            → config.yaml model.default
          provider         → config.yaml model.provider
        """
        from pathlib import Path as _P
        name = agent_id.removeprefix("hermes-profile-")
        real_home = _real_hermes_home()
        if name == "default":
            profile_dir = real_home
        else:
            profile_dir = real_home / "profiles" / name

        if not (profile_dir / "config.yaml").exists():
            return _error(f"Profile '{name}' not found", status=404)

        try:
            # soul
            if "soul" in body:
                (profile_dir / "SOUL.md").write_text(body["soul"], encoding="utf-8")

            # description
            if "description" in body:
                _patch_profile_description(profile_dir, body["description"])

            # api_server port / key
            api_port = body.get("api_server_port")
            api_key  = body.get("api_server_key")
            if api_port is not None or api_key is not None:
                _patch_profile_api_server(
                    profile_dir,
                    port=int(api_port) if api_port is not None else None,
                    key=str(api_key) if api_key is not None else None,
                )

            # model / provider
            if "model" in body or "provider" in body:
                _patch_profile_model(
                    profile_dir,
                    model=body.get("model"),
                    provider=body.get("provider"),
                )

        except Exception as exc:
            logger.exception("update profile failed")
            return _error(str(exc), status=500)

        info = _read_profile_full_config(profile_dir)
        gw_running = _profile_gateway_running(profile_dir, port=info.get("port", 0))

        # 配置已更新，后台重启 gateway 使改动生效（不阻塞响应）
        _restart_profile_gateway(name)

        return _json_response(_profile_to_dict(name, profile_dir, info, gw_running))

    async def _handle_delete(self, request: "web.Request") -> "web.Response":
        """删除 Agent = 调用 hermes profile delete，删除 ~/.hermes/profiles/{name}。"""
        agent_id = request.match_info["id"]
        # id 格式为 "hermes-profile-{name}"，或直接传 name
        name = agent_id.removeprefix("hermes-profile-")

        # 禁止删除 default profile
        if name == "default":
            return _error("Cannot delete the default profile", status=400)

        try:
            import asyncio, os, shutil
            loop = asyncio.get_event_loop()

            real_home = _real_hermes_home()
            os.environ["HERMES_HOME"] = str(real_home)

            profile_dir = real_home / "profiles" / name
            if not profile_dir.is_dir():
                return _error(f"Profile '{name}' not found", status=404)

            # 直接删除目录，绕过 delete_profile 的 HERMES_HOME 路径解析问题
            def _do_delete():
                import subprocess
                from pathlib import Path as _P

                # 1. 通过扫描 plist 内容找到所有引用该 profile 的 launchd 服务并卸载
                # （gateway install 可能生成 hash 命名的 plist，名称与 profile 不对应）
                launch_agents = _P.home() / "Library" / "LaunchAgents"
                profile_str = str(profile_dir)
                if launch_agents.is_dir():
                    for plist in launch_agents.glob("ai.hermes.gateway*.plist"):
                        try:
                            content = plist.read_text(encoding="utf-8")
                            if profile_str in content:
                                subprocess.run(
                                    ["launchctl", "unload", "-w", str(plist)],
                                    capture_output=True, timeout=10,
                                )
                                plist.unlink()
                                logger.info("Removed launchd plist %s", plist.name)
                        except Exception as e:
                            logger.warning("Failed to remove plist %s: %s", plist, e)

                # 2. 删除 wrapper script
                wrapper = _P.home() / ".local" / "bin" / name
                if wrapper.exists():
                    wrapper.unlink()

                # 3. 删除 profile 目录
                shutil.rmtree(profile_dir, ignore_errors=True)

            await loop.run_in_executor(None, _do_delete)
        except Exception as exc:
            logger.exception("delete profile failed")
            return _error(str(exc), status=500)

        return _json_response({"deleted": name})

    async def _handle_start(self, request: "web.Request") -> "web.Response":
        agent_id = request.match_info["id"]
        try:
            instance = await self._manager.start_agent(agent_id)
        except KeyError:
            return _error(f"Agent {agent_id!r} not found", status=404)
        except RuntimeError as exc:
            return _error(str(exc), status=409)
        except Exception as exc:
            return _error(str(exc), status=500)
        return _json_response(instance.to_dict())

    async def _handle_stop(self, request: "web.Request") -> "web.Response":
        agent_id = request.match_info["id"]
        try:
            await self._manager.stop_agent(agent_id)
        except KeyError:
            return _error(f"Agent {agent_id!r} not found", status=404)
        except RuntimeError as exc:
            return _error(str(exc), status=409)
        instance = self._manager.get_instance(agent_id)
        return _json_response(instance.to_dict())

    async def _handle_restart(self, request: "web.Request") -> "web.Response":
        agent_id = request.match_info["id"]
        try:
            instance = await self._manager.restart_agent(agent_id)
        except KeyError:
            return _error(f"Agent {agent_id!r} not found", status=404)
        except Exception as exc:
            return _error(str(exc), status=500)
        return _json_response(instance.to_dict())

    async def _handle_status(self, request: "web.Request") -> "web.Response":
        agent_id = request.match_info["id"]
        try:
            instance = self._manager.get_instance(agent_id)
        except KeyError:
            return _error(f"Agent {agent_id!r} not found", status=404)
        return _json_response({
            "id":          instance.config.id,
            "name":        instance.config.name,
            "status":      instance.status.value,
            "actual_port": instance.actual_port,
            "started_at":  instance.started_at,
            "error":       instance.error,
        })
