from __future__ import annotations

"""
AgentAPIAdapter — subclass of APIServerAdapter that injects per-agent
soul / model / tools into every AIAgent it creates.

This is the ONLY file that needs review when api_server.py is upgraded,
because _create_agent() is deliberately replicated here rather than
patched into the parent class.
"""

import logging
from typing import Any, Optional

from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter

from .models import AgentConfig

logger = logging.getLogger(__name__)


class AgentAPIAdapter(APIServerAdapter):
    """
    APIServerAdapter 的子类，将 AgentConfig 的 soul / model / tools
    注入到 _create_agent()，其余路由和 SSE 逻辑全部继承自父类。
    """

    def __init__(self, agent_cfg: AgentConfig) -> None:
        # pkg launcher 将 HERMES_HOME 设为 /usr/local/hermes（只读安装目录），
        # 强制修正为用户真实数据目录 ~/.hermes，否则 cron/state 等写操作会报错。
        import os
        from pathlib import Path
        hermes_home = os.environ.get("HERMES_HOME", "")
        if not hermes_home or not os.access(hermes_home, os.W_OK):
            os.environ["HERMES_HOME"] = str(Path.home() / ".hermes")

        platform_cfg = PlatformConfig(
            enabled=True,
            extra={
                "host": agent_cfg.host,
                "port": agent_cfg.port,
                "key":  agent_cfg.api_key,
            },
        )
        super().__init__(platform_cfg)

        self._soul          = agent_cfg.soul
        self._agent_model   = agent_cfg.model
        self._agent_tools   = list(agent_cfg.tools or [])
        self._agent_max_iter = agent_cfg.max_iterations
        self._agent_id      = agent_cfg.id
        self._agent_name    = agent_cfg.name

    # ------------------------------------------------------------------
    # Override: inject soul / model / tools
    # ------------------------------------------------------------------

    def _create_agent(
        self,
        ephemeral_system_prompt: Optional[str] = None,
        session_id: Optional[str] = None,
        stream_delta_callback=None,
        tool_progress_callback=None,
        tool_start_callback=None,
        tool_complete_callback=None,
        gateway_session_key: Optional[str] = None,
        model_override: Optional[str] = None,
    ) -> Any:
        from run_agent import AIAgent
        from gateway.run import (
            GatewayRunner,
            _load_gateway_config,
            _resolve_gateway_model,
            _resolve_runtime_agent_kwargs,
        )
        from hermes_cli.tools_config import _get_platform_tools

        runtime_kwargs   = _resolve_runtime_agent_kwargs()
        reasoning_config = GatewayRunner._load_reasoning_config()
        fallback_model   = GatewayRunner._load_fallback_model()
        user_config      = _load_gateway_config()

        # model priority: request body > AgentConfig.model > global config
        model = self._agent_model or _resolve_gateway_model()
        if model_override:
            try:
                from hermes_cli.config import get_compatible_custom_providers
                for entry in get_compatible_custom_providers(user_config):
                    if (entry.get("name") == model_override
                            or entry.get("model") == model_override):
                        runtime_kwargs["provider"] = "custom"
                        runtime_kwargs["base_url"]  = str(entry.get("base_url", "")).strip()
                        runtime_kwargs["api_key"]   = str(entry.get("api_key", "")).strip()
                        if entry.get("model"):
                            model = str(entry["model"]).strip()
                        break
            except Exception:
                pass

        # soul priority: per-request override > AgentConfig.soul
        effective_soul = ephemeral_system_prompt or self._soul or None

        # tools: AgentConfig.tools wins; empty → inherit global api_server toolset
        if self._agent_tools:
            enabled_toolsets = sorted(self._agent_tools)
        else:
            enabled_toolsets = sorted(_get_platform_tools(user_config, "api_server"))

        return AIAgent(
            model=model,
            **runtime_kwargs,
            max_iterations=self._agent_max_iter,
            quiet_mode=True,
            verbose_logging=False,
            ephemeral_system_prompt=effective_soul,
            enabled_toolsets=enabled_toolsets,
            session_id=session_id,
            platform="api_server",
            stream_delta_callback=stream_delta_callback,
            tool_progress_callback=tool_progress_callback,
            tool_start_callback=tool_start_callback,
            tool_complete_callback=tool_complete_callback,
            session_db=self._ensure_session_db(),
            fallback_model=fallback_model,
            reasoning_config=reasoning_config,
            gateway_session_key=gateway_session_key,
        )
