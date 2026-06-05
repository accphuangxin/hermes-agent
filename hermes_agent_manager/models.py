from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentStatus(str, Enum):
    STOPPED  = "stopped"
    STARTING = "starting"
    RUNNING  = "running"
    STOPPING = "stopping"
    ERROR    = "error"


@dataclass
class AgentConfig:
    # ── 身份 ─────────────────────────────────────────────────────────
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""

    # ── 人格（系统提示词） ────────────────────────────────────────────
    soul: str = ""

    # ── 网络 ─────────────────────────────────────────────────────────
    port: int = 0              # 0 = 自动从 8700-8999 分配空闲端口
    host: str = "127.0.0.1"
    api_key: str = ""          # Bearer token，connect() 强制非空

    # ── 模型 ─────────────────────────────────────────────────────────
    model: Optional[str] = None    # None = 继承全局 config.yaml
    provider: Optional[str] = None
    base_url: Optional[str] = None

    # ── 能力 ─────────────────────────────────────────────────────────
    tools: List[str] = field(default_factory=list)  # 空 = 继承全局工具集
    max_iterations: int = 90

    # ── 运行策略 ─────────────────────────────────────────────────────
    auto_start: bool = False   # 管理器启动时自动拉起

    # ── 元数据 ───────────────────────────────────────────────────────
    meta: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id":            self.id,
            "name":          self.name,
            "description":   self.description,
            "soul":          self.soul,
            "port":          self.port,
            "host":          self.host,
            "api_key":       self.api_key,
            "model":         self.model,
            "provider":      self.provider,
            "base_url":      self.base_url,
            "tools":         self.tools,
            "max_iterations": self.max_iterations,
            "auto_start":    self.auto_start,
            "meta":          self.meta,
            "created_at":    self.created_at,
            "updated_at":    self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AgentConfig":
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            name=d.get("name", ""),
            description=d.get("description", ""),
            soul=d.get("soul", ""),
            port=int(d.get("port", 0)),
            host=d.get("host", "127.0.0.1"),
            api_key=d.get("api_key", ""),
            model=d.get("model") or None,
            provider=d.get("provider") or None,
            base_url=d.get("base_url") or None,
            tools=list(d.get("tools") or []),
            max_iterations=int(d.get("max_iterations", 90)),
            auto_start=bool(d.get("auto_start", False)),
            meta=dict(d.get("meta") or {}),
            created_at=float(d.get("created_at", time.time())),
            updated_at=float(d.get("updated_at", time.time())),
        )


@dataclass
class AgentInstance:
    """运行时快照，不持久化到 DB。"""
    config: AgentConfig
    status: AgentStatus = AgentStatus.STOPPED
    actual_port: int = 0
    error: str = ""
    started_at: Optional[float] = None
    adapter: Optional[Any] = None  # AgentAPIAdapter 实例（运行时持有）

    def to_dict(self) -> Dict[str, Any]:
        d = self.config.to_dict()
        d.update({
            "status":      self.status.value,
            "actual_port": self.actual_port,
            "error":       self.error,
            "started_at":  self.started_at,
        })
        return d
