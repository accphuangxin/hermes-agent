"""
hermes_agent_manager — multi-agent independent-port manager for hermes-agent.

Zero-invasive: does not modify any hermes-agent source files.
Subclasses APIServerAdapter to inject per-agent soul / model / tools.

Quick start::

    python -m hermes_agent_manager          # default: control port 8640
    python -m hermes_agent_manager --port 8640 --api-key my-secret

Public API::

    from hermes_agent_manager import AgentManager, AgentConfig, AgentStatus
"""

__version__ = "0.1.0"

from .manager import AgentManager
from .models import AgentConfig, AgentInstance, AgentStatus

__all__ = [
    "AgentManager",
    "AgentConfig",
    "AgentInstance",
    "AgentStatus",
]
