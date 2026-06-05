from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import AgentConfig

_CREATE_TABLE = """
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
    tools           TEXT NOT NULL DEFAULT '[]',
    max_iterations  INTEGER NOT NULL DEFAULT 90,
    auto_start      INTEGER NOT NULL DEFAULT 0,
    meta            TEXT NOT NULL DEFAULT '{}',
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
)
"""

_UPDATABLE_FIELDS = {
    "name", "description", "soul", "port", "host", "api_key",
    "model", "provider", "base_url", "tools", "max_iterations",
    "auto_start", "meta",
}


def _default_db_path() -> str:
    # The pkg launcher sets HERMES_HOME=/usr/local/hermes (the install prefix,
    # not the user data dir). That path is read-only, so we must never write
    # the DB there. Fall back to ~/.hermes when HERMES_HOME points to a
    # non-writable or system-owned directory.
    import os
    try:
        from hermes_constants import get_hermes_home
        candidate = get_hermes_home()
        if not os.access(str(candidate), os.W_OK):
            candidate = Path.home() / ".hermes"
        candidate.mkdir(parents=True, exist_ok=True)
        return str(candidate / "agent_manager.db")
    except Exception:
        fallback = Path.home() / ".hermes"
        fallback.mkdir(parents=True, exist_ok=True)
        return str(fallback / "agent_manager.db")


class AgentStore:
    """SQLite-backed persistence for AgentConfig records."""

    def __init__(self, db_path: Optional[str] = None):
        self._path = db_path or _default_db_path()
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()

    # ── 序列化辅助 ────────────────────────────────────────────────────

    @staticmethod
    def _row_to_cfg(row: sqlite3.Row) -> AgentConfig:
        d = dict(row)
        d["tools"] = json.loads(d.get("tools") or "[]")
        d["meta"]  = json.loads(d.get("meta")  or "{}")
        d["auto_start"] = bool(d.get("auto_start", 0))
        return AgentConfig.from_dict(d)

    @staticmethod
    def _cfg_to_params(cfg: AgentConfig) -> Dict[str, Any]:
        return {
            "id":            cfg.id,
            "name":          cfg.name,
            "description":   cfg.description,
            "soul":          cfg.soul,
            "port":          cfg.port,
            "host":          cfg.host,
            "api_key":       cfg.api_key,
            "model":         cfg.model,
            "provider":      cfg.provider,
            "base_url":      cfg.base_url,
            "tools":         json.dumps(cfg.tools),
            "max_iterations": cfg.max_iterations,
            "auto_start":    int(cfg.auto_start),
            "meta":          json.dumps(cfg.meta),
            "created_at":    cfg.created_at,
            "updated_at":    cfg.updated_at,
        }

    # ── CRUD ──────────────────────────────────────────────────────────

    def create(self, cfg: AgentConfig) -> AgentConfig:
        params = self._cfg_to_params(cfg)
        self._conn.execute(
            """
            INSERT INTO agents
              (id, name, description, soul, port, host, api_key,
               model, provider, base_url, tools, max_iterations,
               auto_start, meta, created_at, updated_at)
            VALUES
              (:id, :name, :description, :soul, :port, :host, :api_key,
               :model, :provider, :base_url, :tools, :max_iterations,
               :auto_start, :meta, :created_at, :updated_at)
            """,
            params,
        )
        self._conn.commit()
        return cfg

    def get(self, agent_id: str) -> Optional[AgentConfig]:
        row = self._conn.execute(
            "SELECT * FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()
        return self._row_to_cfg(row) if row else None

    def get_by_name(self, name: str) -> Optional[AgentConfig]:
        row = self._conn.execute(
            "SELECT * FROM agents WHERE name = ?", (name,)
        ).fetchone()
        return self._row_to_cfg(row) if row else None

    def list_all(self) -> List[AgentConfig]:
        rows = self._conn.execute(
            "SELECT * FROM agents ORDER BY created_at ASC"
        ).fetchall()
        return [self._row_to_cfg(r) for r in rows]

    def list_auto_start(self) -> List[AgentConfig]:
        rows = self._conn.execute(
            "SELECT * FROM agents WHERE auto_start = 1 ORDER BY created_at ASC"
        ).fetchall()
        return [self._row_to_cfg(r) for r in rows]

    def update(self, agent_id: str, patch: Dict[str, Any]) -> AgentConfig:
        cfg = self.get(agent_id)
        if cfg is None:
            raise KeyError(f"Agent {agent_id!r} not found")

        allowed = {k: v for k, v in patch.items() if k in _UPDATABLE_FIELDS}
        if not allowed:
            return cfg

        sets = []
        vals: List[Any] = []
        for k, v in allowed.items():
            sets.append(f"{k} = ?")
            if k == "tools":
                vals.append(json.dumps(list(v or [])))
            elif k == "meta":
                vals.append(json.dumps(dict(v or {})))
            elif k == "auto_start":
                vals.append(int(bool(v)))
            else:
                vals.append(v)

        sets.append("updated_at = ?")
        vals.append(time.time())
        vals.append(agent_id)

        self._conn.execute(
            f"UPDATE agents SET {', '.join(sets)} WHERE id = ?", vals
        )
        self._conn.commit()
        return self.get(agent_id)

    def delete(self, agent_id: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM agents WHERE id = ?", (agent_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()
