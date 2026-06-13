from __future__ import annotations

import asyncio
import logging
import platform
import socket
import time
from pathlib import Path
from typing import Dict, List, Optional

from .adapter import AgentAPIAdapter
from .models import AgentConfig, AgentInstance, AgentStatus
from .store import AgentStore

logger = logging.getLogger(__name__)

_FREE_PORT_START   = 8700
_FREE_PORT_END     = 8999
_GC_INTERVAL       = 60    # seconds between orphan-gc runs
_START_TIMEOUT     = 30    # seconds to wait for agent health check after connect()
_START_POLL_INTERVAL = 0.5 # seconds between health check polls


def _real_hermes_home() -> Path:
    """返回用户真实的 ~/.hermes，忽略 HERMES_HOME 环境变量。"""
    return Path.home() / ".hermes"


def _gc_orphan_gateway_services() -> None:
    """扫描 launchd/systemd 里的 hermes gateway 服务，卸载并删除 profile 目录已不存在的孤儿服务。

    处理两类场景：
    1. profile 目录被删除后 plist 未清理（launchd KeepAlive 会不断重建目录）
    2. 大小写不一致：plist 里 HERMES_HOME 指向大写路径，但实际 profiles 目录是小写
    """
    import subprocess, shutil

    real_home = _real_hermes_home()
    profiles_dir = real_home / "profiles"

    # 收集所有已知 profile 名称（小写，用于大小写不敏感比较）
    known = set()
    if profiles_dir.is_dir():
        known = {d.name.lower() for d in profiles_dir.iterdir() if d.is_dir()}
    # default profile 始终合法
    known.add("default")

    if platform.system() == "Darwin":
        _gc_launchd(real_home, profiles_dir, known)
    else:
        _gc_systemd(real_home, profiles_dir, known)


def _gc_launchd(real_home: Path, profiles_dir: Path, known: set) -> None:
    import subprocess
    launch_agents = Path.home() / "Library" / "LaunchAgents"
    if not launch_agents.is_dir():
        return

    for plist in launch_agents.glob("ai.hermes.gateway*.plist"):
        try:
            content = plist.read_text(encoding="utf-8")
        except Exception:
            continue

        # 从 plist 内容提取 HERMES_HOME 值
        hermes_home = _extract_plist_hermes_home(content)
        if not hermes_home:
            continue

        profile_path = Path(hermes_home)

        # default profile 跳过
        if profile_path == real_home:
            continue

        # 判断是否是合法 profile：目录存在 且 名称（大小写不敏感）在已知集合里
        profile_exists = profile_path.is_dir()
        name_known = profile_path.name.lower() in known

        if profile_exists and name_known:
            continue

        # 孤儿服务：卸载 + 删 plist + 删目录
        label = _extract_plist_label(content) or plist.stem
        logger.warning(
            "GC: orphan gateway service %s (HERMES_HOME=%s, dir_exists=%s, name_known=%s) — removing",
            label, hermes_home, profile_exists, name_known,
        )
        subprocess.run(["launchctl", "unload", "-w", str(plist)], capture_output=True, timeout=10)
        plist.unlink(missing_ok=True)
        if profile_path.is_dir():
            import shutil as _shutil
            _shutil.rmtree(profile_path, ignore_errors=True)
            logger.info("GC: removed orphan profile dir %s", profile_path)


def _gc_systemd(real_home: Path, profiles_dir: Path, known: set) -> None:
    import subprocess
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    if not unit_dir.is_dir():
        return

    for unit in unit_dir.glob("hermes-gateway*.service"):
        try:
            content = unit.read_text(encoding="utf-8")
        except Exception:
            continue

        hermes_home = _extract_systemd_hermes_home(content)
        if not hermes_home:
            continue

        profile_path = Path(hermes_home)
        if profile_path == real_home:
            continue

        profile_exists = profile_path.is_dir()
        name_known = profile_path.name.lower() in known

        if profile_exists and name_known:
            continue

        logger.warning(
            "GC: orphan systemd unit %s (HERMES_HOME=%s) — removing", unit.name, hermes_home,
        )
        subprocess.run(["systemctl", "--user", "stop",    unit.stem], capture_output=True, timeout=10)
        subprocess.run(["systemctl", "--user", "disable", unit.stem], capture_output=True, timeout=10)
        unit.unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, timeout=10)
        if profile_path.is_dir():
            import shutil as _shutil
            _shutil.rmtree(profile_path, ignore_errors=True)
            logger.info("GC: removed orphan profile dir %s", profile_path)


def _extract_plist_hermes_home(content: str) -> str:
    """从 plist XML 内容中提取 HERMES_HOME 环境变量值。"""
    import re
    m = re.search(r'<key>HERMES_HOME</key>\s*<string>([^<]+)</string>', content)
    return m.group(1).strip() if m else ""


def _extract_plist_label(content: str) -> str:
    """从 plist XML 内容中提取 Label 值。"""
    import re
    m = re.search(r'<key>Label</key>\s*<string>([^<]+)</string>', content)
    return m.group(1).strip() if m else ""


def _extract_systemd_hermes_home(content: str) -> str:
    """从 systemd unit 文件中提取 HERMES_HOME 值。"""
    import re
    m = re.search(r'Environment=HERMES_HOME=(.+)', content)
    return m.group(1).strip() if m else ""


def _find_free_port(start: int = _FREE_PORT_START, end: int = _FREE_PORT_END) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in [{start}, {end}]")


class AgentManager:
    """
    Manages the lifecycle of multiple AgentAPIAdapter instances,
    each listening on its own port.

    Usage::

        manager = AgentManager(db_path="~/.hermes/agent_manager.db",
                               management_port=8640)
        await manager.startup()          # load DB + auto-start + control server
        ...
        await manager.shutdown()         # stop all agents + control server
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        management_port: int = 8640,
        management_host: str = "127.0.0.1",
        management_api_key: str = "",
    ) -> None:
        self._store = AgentStore(db_path)
        self._instances: Dict[str, AgentInstance] = {}
        self._lock = asyncio.Lock()
        self._gc_task: Optional[asyncio.Task] = None

        # ControlServer import is deferred to avoid circular imports
        from .control_server import ControlServer
        self._control = ControlServer(
            manager=self,
            host=management_host,
            port=management_port,
            api_key=management_api_key,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """Load all agents from DB, auto-start flagged ones, then start the control server."""
        for cfg in self._store.list_all():
            self._instances[cfg.id] = AgentInstance(config=cfg)
            logger.debug("Loaded agent %r (id=%s)", cfg.name, cfg.id)

        for cfg in self._store.list_auto_start():
            try:
                await self.start_agent(cfg.id)
            except Exception as exc:
                logger.error("Auto-start failed for agent %r: %s", cfg.name, exc)

        await self._control.start()
        # 启动时立即执行一次，清理可能在上次关闭后残留的孤儿服务
        await asyncio.get_event_loop().run_in_executor(None, _gc_orphan_gateway_services)
        self._gc_task = asyncio.ensure_future(self._gc_loop())
        logger.info("AgentManager ready (control: %s:%d)", self._control.host, self._control.port)

    async def shutdown(self) -> None:
        """Stop all running agents and the control server."""
        if self._gc_task:
            self._gc_task.cancel()
            try:
                await self._gc_task
            except asyncio.CancelledError:
                pass
        await self._control.stop()
        for instance in list(self._instances.values()):
            if instance.status == AgentStatus.RUNNING:
                try:
                    await self._do_stop(instance)
                except Exception as exc:
                    logger.error("Error stopping agent %r: %s", instance.config.name, exc)
        self._store.close()
        logger.info("AgentManager shut down")

    async def _gc_loop(self) -> None:
        """定期扫描并清理孤儿 gateway 服务（profile 目录不存在的残留 plist）。"""
        while True:
            await asyncio.sleep(_GC_INTERVAL)
            try:
                await asyncio.get_event_loop().run_in_executor(None, _gc_orphan_gateway_services)
            except Exception as exc:
                logger.warning("GC orphan services error: %s", exc)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_agent(self, cfg: AgentConfig) -> AgentConfig:
        if not cfg.api_key:
            raise ValueError(
                "api_key 未设置。请在创建 Agent 时提供 api_key，"
                "客户端需通过 'Authorization: Bearer <api_key>' 进行认证。"
            )

        if cfg.port == 0:
            cfg.port = _find_free_port()

        async with self._lock:
            # name uniqueness check
            existing = self._store.get_by_name(cfg.name)
            if existing:
                raise ValueError(f"An agent named {cfg.name!r} already exists (id={existing.id})")

            cfg = self._store.create(cfg)
            self._instances[cfg.id] = AgentInstance(config=cfg)

        if cfg.auto_start:
            await self.start_agent(cfg.id)

        return cfg

    async def update_agent(self, agent_id: str, patch: dict) -> AgentConfig:
        async with self._lock:
            instance = self._get_instance(agent_id)
            if instance.status == AgentStatus.RUNNING:
                raise RuntimeError("Stop the agent before updating its config")
            cfg = self._store.update(agent_id, patch)
            instance.config = cfg
        return cfg

    async def delete_agent(self, agent_id: str) -> None:
        await self.stop_agent(agent_id, ignore_not_running=True)
        async with self._lock:
            self._store.delete(agent_id)
            self._instances.pop(agent_id, None)

    # ------------------------------------------------------------------
    # Lifecycle control
    # ------------------------------------------------------------------

    async def start_agent(self, agent_id: str) -> AgentInstance:
        async with self._lock:
            instance = self._get_instance(agent_id)
            if instance.status == AgentStatus.RUNNING:
                return instance
            if instance.status == AgentStatus.STARTING:
                raise RuntimeError(f"Agent {agent_id} is already starting")

            instance.status = AgentStatus.STARTING
            instance.error  = ""

        try:
            if not instance.config.api_key:
                raise ValueError(
                    "api_key 未设置。请先配置 api_key，"
                    "客户端需通过 'Authorization: Bearer <api_key>' 进行认证。"
                )

            adapter = AgentAPIAdapter(instance.config)
            ok = await adapter.connect()
            if not ok:
                raise RuntimeError("adapter.connect() returned False — check api_key and port")

            # 等待 HTTP 健康检查通过，确认服务真正就绪
            host = instance.config.host or "127.0.0.1"
            port = instance.config.port
            health_url = f"http://{host}:{port}/health"
            deadline = time.time() + _START_TIMEOUT
            ready = False
            last_err = ""
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    while time.time() < deadline:
                        try:
                            async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                                if resp.status == 200:
                                    ready = True
                                    break
                                last_err = f"HTTP {resp.status}"
                        except Exception as e:
                            last_err = str(e)
                        await asyncio.sleep(_START_POLL_INTERVAL)
            except ImportError:
                # aiohttp 不可用时跳过健康检查（不应发生，但做保护）
                ready = True

            if not ready:
                await adapter.disconnect()
                raise RuntimeError(
                    f"Agent {instance.config.name!r} 在 {_START_TIMEOUT}s 内未就绪，"
                    f"最后错误: {last_err}。请检查端口 {port} 是否被占用或配置是否正确。"
                )

            async with self._lock:
                instance.adapter     = adapter
                instance.actual_port = instance.config.port
                instance.status      = AgentStatus.RUNNING
                instance.started_at  = time.time()

            logger.info("Agent %r started and healthy on port %d", instance.config.name, instance.actual_port)
        except Exception as exc:
            async with self._lock:
                instance.status = AgentStatus.ERROR
                instance.error  = str(exc)
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
            await self._do_stop(instance)
        except Exception as exc:
            async with self._lock:
                instance.status = AgentStatus.ERROR
                instance.error  = str(exc)
            raise

    async def restart_agent(self, agent_id: str) -> AgentInstance:
        await self.stop_agent(agent_id, ignore_not_running=True)
        return await self.start_agent(agent_id)

    async def _do_stop(self, instance: AgentInstance) -> None:
        if instance.adapter is not None:
            try:
                await instance.adapter.disconnect()
            finally:
                instance.adapter = None
        instance.status = AgentStatus.STOPPED
        logger.info("Agent %r stopped", instance.config.name)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_instance(self, agent_id: str) -> AgentInstance:
        return self._get_instance(agent_id)

    def list_instances(self) -> List[AgentInstance]:
        return list(self._instances.values())

    def _get_instance(self, agent_id: str) -> AgentInstance:
        instance = self._instances.get(agent_id)
        if instance is None:
            raise KeyError(f"Agent {agent_id!r} not found")
        return instance
