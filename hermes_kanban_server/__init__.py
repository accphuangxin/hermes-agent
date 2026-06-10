"""
Hermes Kanban API Server

A REST API server for managing Kanban boards, tasks, workflows, and scenarios.
"""

__version__ = "0.1.0"

# Lazy import to avoid dependency errors when using the CLI
def __getattr__(name):
    if name == "KanbanAPIServer":
        from .server import KanbanAPIServer
        return KanbanAPIServer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["KanbanAPIServer"]
