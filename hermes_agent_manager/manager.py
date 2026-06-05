from __future__ import annotations

import asyncio
import logging
import socket
import time
from typing import Dict, List, Optional

from .adapter import AgentAPIAdapter
from .models import AgentConfig, AgentInstance, AgentStatus
from .store import AgentStore

logger = logging.getLogger(__name__)

_FREE_PORT_START = 8700
_FREE_PORT_END   = 8999


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
        logger.info("AgentManager ready (control: %s:%d)", self._control.host, self._control.port)

    async def shutdown(self) -> None:
        """Stop all running agents and the control server."""
        await self._control.stop()
        for instance in list(self._instances.values()):
            if instance.status == AgentStatus.RUNNING:
                try:
                    await self._do_stop(instance)
                except Exception as exc:
                    logger.error("Error stopping agent %r: %s", instance.config.name, exc)
        self._store.close()
        logger.info("AgentManager shut down")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_agent(self, cfg: AgentConfig) -> AgentConfig:
        if not cfg.api_key:
            raise ValueError("api_key is required (api_server enforces Bearer auth)")

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
            adapter = AgentAPIAdapter(instance.config)
            ok = await adapter.connect()
            if not ok:
                raise RuntimeError("adapter.connect() returned False — check api_key and port")

            async with self._lock:
                instance.adapter     = adapter
                instance.actual_port = instance.config.port
                instance.status      = AgentStatus.RUNNING
                instance.started_at  = time.time()

            logger.info("Agent %r started on port %d", instance.config.name, instance.actual_port)
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
