"""Kanban API Server main class"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from aiohttp import web

from .auth import create_auth_middleware
from .routes import health, boards, tasks


logger = logging.getLogger(__name__)


class KanbanAPIServer:
    """
    REST API Server for Hermes Kanban.

    Provides endpoints for:
    - Board management
    - Task CRUD and operations
    - Workflow management (Phase 2)
    - Scenario management (Phase 3)
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8650,
        api_key: Optional[str] = None,
        boards_root: Optional[str] = None,
    ):
        """
        Initialize Kanban API Server.

        Args:
            host: Bind host (default: 127.0.0.1)
            port: Bind port (default: 8650)
            api_key: Optional API key for Bearer token authentication
            boards_root: Root directory for boards (default: ~/.hermes/kanban/boards)
        """
        self.host = host
        self.port = port
        self._api_key = api_key

        if boards_root:
            self._boards_root = Path(boards_root).expanduser()
        else:
            self._boards_root = Path.home() / ".hermes" / "kanban" / "boards"

        # Ensure boards root exists
        self._boards_root.mkdir(parents=True, exist_ok=True)

        # Create application with auth middleware
        middlewares = [create_auth_middleware(api_key)]
        self._app = web.Application(middlewares=middlewares)

        # Setup routes
        self._setup_routes()

        # Runner for lifecycle management
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    def _setup_routes(self):
        """Register all API routes"""

        # Health & Stats
        self._app.router.add_get("/v1/health", health.health_check)
        self._app.router.add_get("/v1/stats", health.stats)
        self._app.router.add_get("/v1/boards/{board}/stats", health.board_stats)

        # Board Management
        self._app.router.add_post("/v1/boards", boards.create_board)
        self._app.router.add_get("/v1/boards", boards.list_boards)
        self._app.router.add_get("/v1/boards/{slug}", boards.get_board)
        self._app.router.add_patch("/v1/boards/{slug}", boards.update_board)
        self._app.router.add_delete("/v1/boards/{slug}", boards.delete_board)
        self._app.router.add_post("/v1/boards/{slug}/init", boards.init_board)

        # Task CRUD
        self._app.router.add_post("/v1/boards/{board}/tasks", tasks.create_task)
        self._app.router.add_get("/v1/boards/{board}/tasks", tasks.list_tasks)
        self._app.router.add_get("/v1/boards/{board}/tasks/{task_id}", tasks.get_task)
        self._app.router.add_patch("/v1/boards/{board}/tasks/{task_id}", tasks.update_task)
        self._app.router.add_delete("/v1/boards/{board}/tasks/{task_id}", tasks.delete_task)

        # Task Operations
        self._app.router.add_post("/v1/boards/{board}/tasks/{task_id}/claim", tasks.claim_task)
        self._app.router.add_post("/v1/boards/{board}/tasks/{task_id}/complete", tasks.complete_task)
        self._app.router.add_post("/v1/boards/{board}/tasks/{task_id}/block", tasks.block_task)
        self._app.router.add_post("/v1/boards/{board}/tasks/{task_id}/unblock", tasks.unblock_task)
        self._app.router.add_post("/v1/boards/{board}/tasks/{task_id}/archive", tasks.archive_task)
        self._app.router.add_post("/v1/boards/{board}/tasks/{task_id}/reset", tasks.reset_task)

        # Task Dependencies
        self._app.router.add_post("/v1/boards/{board}/tasks/{task_id}/link", tasks.link_tasks)
        self._app.router.add_delete("/v1/boards/{board}/tasks/{task_id}/link", tasks.unlink_tasks)
        self._app.router.add_get("/v1/boards/{board}/tasks/{task_id}/parents", tasks.get_parents)
        self._app.router.add_get("/v1/boards/{board}/tasks/{task_id}/children", tasks.get_children)

        # Task Conversation
        self._app.router.add_get("/v1/boards/{board}/tasks/{task_id}/conversation", tasks.get_task_conversation)
        self._app.router.add_get("/v1/boards/{board}/tasks/{task_id}/conversation/summary", tasks.get_task_conversation_summary)

        # Task Execution Logs
        self._app.router.add_get("/v1/boards/{board}/tasks/{task_id}/events", tasks.get_task_events)
        self._app.router.add_get("/v1/boards/{board}/tasks/{task_id}/runs", tasks.get_task_runs)

        # Task Thread Messages (主任务+所有子任务消息聚合)
        self._app.router.add_get("/v1/boards/{board}/tasks/{task_id}/thread-messages", tasks.get_task_thread_messages)

        # Board Operations
        self._app.router.add_post("/v1/boards/{board}/trigger", boards.trigger_board)

        logger.info("API routes registered")

    async def start(self):
        """Start the API server"""
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

        logger.info(f"Kanban API Server started on http://{self.host}:{self.port}")
        print(f"🚀 Kanban API Server running on http://{self.host}:{self.port}")

        if self._api_key:
            print(f"🔒 Authentication: Bearer token required")
        else:
            print(f"⚠️  Authentication: Disabled (no API key configured)")

        print(f"📋 Boards root: {self._boards_root}")
        print(f"")
        print(f"Endpoints:")
        print(f"  GET  /v1/health              - Health check")
        print(f"  GET  /v1/boards              - List boards")
        print(f"  POST /v1/boards              - Create board")
        print(f"  GET  /v1/boards/{{board}}/tasks  - List tasks")
        print(f"  POST /v1/boards/{{board}}/tasks  - Create task")
        print(f"")
        print(f"Press Ctrl+C to stop")

    async def stop(self):
        """Stop the API server"""
        if self._runner:
            await self._runner.cleanup()
            logger.info("Kanban API Server stopped")

    async def run_forever(self):
        """Run the server until interrupted"""
        try:
            await self.start()
            # Keep running
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("Received KeyboardInterrupt, shutting down...")
        finally:
            await self.stop()


def run_server(
    host: str = "127.0.0.1",
    port: int = 8650,
    api_key: Optional[str] = None,
):
    """
    Run Kanban API Server (blocking).

    Args:
        host: Bind host
        port: Bind port
        api_key: Optional API key for authentication
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    server = KanbanAPIServer(host=host, port=port, api_key=api_key)

    try:
        asyncio.run(server.run_forever())
    except KeyboardInterrupt:
        print("\n👋 Kanban API Server stopped")
