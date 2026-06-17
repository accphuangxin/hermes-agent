"""Task CRUD and operations endpoints"""

import json
from aiohttp import web


def _safe_json(value):
    """尝试把字符串解析为 JSON，失败则原样返回。"""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


async def create_task(request: web.Request) -> web.Response:
    """
    Create a new task on a board.

    Request body:
        {
            "title": "Task title",
            "body": "Optional task description",
            "assignee": "agent-name",
            "priority": 5,
            "metadata": {"key": "value"}
        }

    Returns:
        201 with created task ID
    """
    board_slug = request.match_info["board"]

    try:
        data = await request.json()
        from hermes_cli import kanban_db

        conn = kanban_db.connect(board=board_slug)
        try:
            task_id = kanban_db.create_task(
                conn,
                title=data.get("title", ""),
                body=data.get("body"),
                assignee=data.get("assignee"),
                priority=data.get("priority", 0),
                skills=data.get("skills"),
                max_retries=data.get("max_retries"),
                max_runtime_seconds=data.get("max_runtime_seconds"),
                tenant=data.get("tenant"),
                session_id=data.get("session_id"),
            )

            return web.json_response(
                {"task_id": task_id, "board": board_slug},
                status=201
            )
        finally:
            conn.close()

    except FileNotFoundError:
        return web.json_response(
            {"error": f"Board '{board_slug}' not found"},
            status=404
        )
    except json.JSONDecodeError:
        return web.json_response(
            {"error": "Invalid JSON"},
            status=400
        )
    except Exception as e:
        return web.json_response(
            {"error": str(e)},
            status=500
        )


async def list_tasks(request: web.Request) -> web.Response:
    """
    List tasks on a board with optional filtering.

    Query parameters:
        - status: Filter by status (ready, running, done, blocked, failed, archived)
        - assignee: Filter by assignee
        - limit: Maximum number of tasks to return

    Returns:
        JSON array of tasks
    """
    board_slug = request.match_info["board"]

    try:
        from hermes_cli import kanban_db

        conn = kanban_db.connect(board=board_slug)
        try:
            # Get query parameters
            status_filter = request.query.get("status")
            assignee_filter = request.query.get("assignee")
            limit = int(request.query.get("limit", 100))

            # List tasks
            tasks = kanban_db.list_tasks(
                conn,
                status=status_filter,
                assignee=assignee_filter,
            )

            # Apply limit
            tasks = tasks[:limit]

            # Convert to dict format with parents and children
            tasks_data = []
            for task in tasks:
                # Get parents and children for each task
                parent_ids = kanban_db.parent_ids(conn, task.id)
                child_ids = kanban_db.child_ids(conn, task.id)

                # Fetch full task info for parents and children
                parents = []
                for pid in parent_ids:
                    p = kanban_db.get_task(conn, pid)
                    if p:
                        parents.append({"id": p.id, "title": p.title})

                children = []
                for cid in child_ids:
                    c = kanban_db.get_task(conn, cid)
                    if c:
                        children.append({"id": c.id, "title": c.title})

                tasks_data.append({
                    "id": task.id,
                    "title": task.title,
                    "body": task.body,
                    "status": task.status,
                    "assignee": task.assignee,
                    "priority": task.priority,
                    "created_at": task.created_at,
                    "started_at": task.started_at,
                    "completed_at": task.completed_at,
                    "tenant": task.tenant,
                    "session_id": task.session_id,
                    "parents": parents,
                    "children": children,
                })

            return web.json_response(tasks_data)
        finally:
            conn.close()

    except FileNotFoundError:
        return web.json_response(
            {"error": f"Board '{board_slug}' not found"},
            status=404
        )
    except Exception as e:
        return web.json_response(
            {"error": str(e)},
            status=500
        )


async def get_task(request: web.Request) -> web.Response:
    """
    Get detailed task information.

    Returns:
        JSON with full task details
    """
    board_slug = request.match_info["board"]
    task_id = request.match_info["task_id"]

    try:
        from hermes_cli import kanban_db

        conn = kanban_db.connect(board=board_slug)
        try:
            task = kanban_db.get_task(conn, task_id)

            if not task:
                return web.json_response(
                    {"error": f"Task '{task_id}' not found"},
                    status=404
                )

            # Get parents and children
            parent_task_ids = kanban_db.parent_ids(conn, task_id)
            child_task_ids = kanban_db.child_ids(conn, task_id)

            # Fetch full task objects for parents and children
            parents = []
            for pid in parent_task_ids:
                p = kanban_db.get_task(conn, pid)
                if p:
                    parents.append({"id": p.id, "title": p.title})

            children = []
            for cid in child_task_ids:
                c = kanban_db.get_task(conn, cid)
                if c:
                    children.append({"id": c.id, "title": c.title})

            task_data = {
                "id": task.id,
                "title": task.title,
                "body": task.body,
                "status": task.status,
                "assignee": task.assignee,
                "priority": task.priority,
                "created_at": task.created_at,
                "started_at": task.started_at,
                "completed_at": task.completed_at,
                "result": task.result,
                "consecutive_failures": task.consecutive_failures,
                "claim_lock": task.claim_lock,
                "claim_expires": task.claim_expires,
                "worker_pid": task.worker_pid,
                "tenant": task.tenant,
                "created_by": task.created_by,
                "session_id": task.session_id,
                "parents": parents,
                "children": children,
            }

            return web.json_response(task_data)
        finally:
            conn.close()

    except FileNotFoundError:
        return web.json_response(
            {"error": f"Board '{board_slug}' not found"},
            status=404
        )
    except Exception as e:
        return web.json_response(
            {"error": str(e)},
            status=500
        )


async def update_task(request: web.Request) -> web.Response:
    """
    Update task fields.

    Request body can include:
        - title
        - body
        - assignee
        - priority

    Returns:
        200 with updated task info
    """
    board_slug = request.match_info["board"]
    task_id = request.match_info["task_id"]

    try:
        data = await request.json()
        from hermes_cli import kanban_db

        conn = kanban_db.connect(board=board_slug)
        try:
            # Check task exists
            task = kanban_db.get_task(conn, task_id)
            if not task:
                return web.json_response(
                    {"error": f"Task '{task_id}' not found"},
                    status=404
                )

            # Update fields
            if "title" in data:
                kanban_db.update_task_field(conn, task_id, "title", data["title"])
            if "body" in data:
                kanban_db.update_task_field(conn, task_id, "body", data["body"])
            if "assignee" in data:
                kanban_db.update_task_field(conn, task_id, "assignee", data["assignee"])
            if "priority" in data:
                kanban_db.update_task_field(conn, task_id, "priority", data["priority"])

            # Get updated task
            task = kanban_db.get_task(conn, task_id)

            return web.json_response({
                "id": task.id,
                "title": task.title,
                "body": task.body,
                "status": task.status,
                "assignee": task.assignee,
                "priority": task.priority,
            })
        finally:
            conn.close()

    except FileNotFoundError:
        return web.json_response(
            {"error": f"Board '{board_slug}' not found"},
            status=404
        )
    except json.JSONDecodeError:
        return web.json_response(
            {"error": "Invalid JSON"},
            status=400
        )
    except Exception as e:
        return web.json_response(
            {"error": str(e)},
            status=500
        )


async def delete_task(request: web.Request) -> web.Response:
    """
    Delete a task.

    Query parameters:
        - hard: if 'true', permanently delete the task from database
                if omitted or 'false', only archive the task (soft delete)

    Returns:
        204 No Content on success
    """
    board_slug = request.match_info["board"]
    task_id = request.match_info["task_id"]

    # Check if hard delete is requested
    hard_delete = request.query.get("hard", "false").lower() == "true"

    try:
        from hermes_cli import kanban_db

        conn = kanban_db.connect(board=board_slug)
        try:
            # Check task exists
            task = kanban_db.get_task(conn, task_id)
            if not task:
                return web.json_response(
                    {"error": f"Task '{task_id}' not found"},
                    status=404
                )

            if hard_delete:
                # Hard delete: permanently remove from database
                cursor = conn.cursor()

                # 1. Delete all dependency links (both as parent and child)
                cursor.execute("DELETE FROM task_links WHERE parent_id = ? OR child_id = ?",
                              (task_id, task_id))

                # 2. Delete the task itself
                cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

                conn.commit()
            else:
                # Soft delete: archive task (default, safer)
                kanban_db.archive_task(conn, task_id)

            return web.Response(status=204)
        finally:
            conn.close()

    except FileNotFoundError:
        return web.json_response(
            {"error": f"Board '{board_slug}' not found"},
            status=404
        )
    except Exception as e:
        return web.json_response(
            {"error": str(e)},
            status=500
        )


# Task operations

async def claim_task(request: web.Request) -> web.Response:
    """Claim a task for execution"""
    board_slug = request.match_info["board"]
    task_id = request.match_info["task_id"]

    try:
        from hermes_cli import kanban_db

        conn = kanban_db.connect(board=board_slug)
        try:
            success = kanban_db.claim_task(conn, task_id)

            if success:
                return web.json_response({"message": "Task claimed successfully"})
            else:
                return web.json_response(
                    {"error": "Failed to claim task (already claimed or not ready)"},
                    status=409
                )
        finally:
            conn.close()

    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def complete_task(request: web.Request) -> web.Response:
    """Mark a task as complete"""
    board_slug = request.match_info["board"]
    task_id = request.match_info["task_id"]

    try:
        data = await request.json()
        from hermes_cli import kanban_db

        conn = kanban_db.connect(board=board_slug)
        try:
            kanban_db.complete_task(
                conn,
                task_id,
                result=data.get("result"),
            )

            return web.json_response({"message": "Task completed successfully"})
        finally:
            conn.close()

    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def block_task(request: web.Request) -> web.Response:
    """Block a task"""
    board_slug = request.match_info["board"]
    task_id = request.match_info["task_id"]

    try:
        from hermes_cli import kanban_db

        conn = kanban_db.connect(board=board_slug)
        try:
            kanban_db.block_task(conn, task_id)

            return web.json_response({"message": "Task blocked successfully"})
        finally:
            conn.close()

    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def unblock_task(request: web.Request) -> web.Response:
    """Unblock a task"""
    board_slug = request.match_info["board"]
    task_id = request.match_info["task_id"]

    try:
        from hermes_cli import kanban_db

        conn = kanban_db.connect(board=board_slug)
        try:
            kanban_db.unblock_task(conn, task_id)

            return web.json_response({"message": "Task unblocked successfully"})
        finally:
            conn.close()

    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def archive_task(request: web.Request) -> web.Response:
    """Archive a task"""
    board_slug = request.match_info["board"]
    task_id = request.match_info["task_id"]

    try:
        from hermes_cli import kanban_db

        conn = kanban_db.connect(board=board_slug)
        try:
            kanban_db.archive_task(conn, task_id)

            return web.json_response({"message": "Task archived successfully"})
        finally:
            conn.close()

    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def reset_task(request: web.Request) -> web.Response:
    """
    Reset a task to ready status.

    Recursively resets all child tasks (tasks that depend on this task).

    Clears: status → ready, result, session_id, started_at, completed_at,
            consecutive_failures, claim_lock, claim_expires, worker_pid
    """
    board_slug = request.match_info["board"]
    task_id = request.match_info["task_id"]

    try:
        from hermes_cli import kanban_db

        conn = kanban_db.connect(board=board_slug)
        try:
            # Check task exists
            task = kanban_db.get_task(conn, task_id)
            if not task:
                return web.json_response(
                    {"error": f"Task '{task_id}' not found"},
                    status=404
                )

            # Get all child tasks (recursively)
            def get_all_descendants(tid):
                """Recursively get all descendant tasks"""
                descendants = []
                child_ids = kanban_db.child_ids(conn, tid)
                for cid in child_ids:
                    descendants.append(cid)
                    descendants.extend(get_all_descendants(cid))
                return descendants

            all_descendants = get_all_descendants(task_id)

            # Reset the task and all its descendants
            cursor = conn.cursor()
            reset_sql = """
                UPDATE tasks
                SET status = 'ready',
                    result = NULL,
                    session_id = NULL,
                    started_at = NULL,
                    completed_at = NULL,
                    consecutive_failures = 0,
                    claim_lock = NULL,
                    claim_expires = NULL,
                    worker_pid = NULL
                WHERE id = ?
            """

            # Reset main task
            cursor.execute(reset_sql, (task_id,))

            # Reset all child tasks
            reset_tasks = [{"id": task_id, "title": task.title}]
            for child_id in all_descendants:
                child_task = kanban_db.get_task(conn, child_id)
                if child_task:
                    cursor.execute(reset_sql, (child_id,))
                    reset_tasks.append({"id": child_task.id, "title": child_task.title})

            conn.commit()

            # Get updated task
            task = kanban_db.get_task(conn, task_id)

            message = f"Task '{task.title}' reset to ready"
            if all_descendants:
                message += f" (including {len(all_descendants)} dependent task(s))"

            return web.json_response({
                "message": message,
                "task": {
                    "id": task.id,
                    "title": task.title,
                    "status": task.status
                },
                "reset_count": len(reset_tasks),
                "reset_tasks": reset_tasks
            })
        finally:
            conn.close()

    except FileNotFoundError:
        return web.json_response(
            {"error": f"Board '{board_slug}' not found"},
            status=404
        )
    except Exception as e:
        return web.json_response(
            {"error": f"Internal error: {str(e)}"},
            status=500
        )


# Dependency management

async def link_tasks(request: web.Request) -> web.Response:
    """Create a dependency link between tasks"""
    board_slug = request.match_info["board"]
    task_id = request.match_info["task_id"]

    try:
        data = await request.json()
        parent_id = data.get("parent_id")

        if not parent_id:
            return web.json_response(
                {"error": "Missing required field: parent_id"},
                status=400
            )

        from hermes_cli import kanban_db

        conn = kanban_db.connect(board=board_slug)
        try:
            # 检查任务是否存在
            parent_task = kanban_db.get_task(conn, parent_id)
            child_task = kanban_db.get_task(conn, task_id)

            if not parent_task:
                return web.json_response(
                    {"error": f"Parent task '{parent_id}' not found"},
                    status=404
                )

            if not child_task:
                return web.json_response(
                    {"error": f"Child task '{task_id}' not found"},
                    status=404
                )

            # 创建依赖关系
            kanban_db.link_tasks(conn, parent_id, task_id)

            return web.json_response({
                "message": f"Linked {parent_id} → {task_id}",
                "parent": {
                    "id": parent_task.id,
                    "title": parent_task.title
                },
                "child": {
                    "id": child_task.id,
                    "title": child_task.title
                }
            }, status=201)
        finally:
            conn.close()

    except ValueError as e:
        # link_tasks 函数抛出的业务逻辑错误（循环依赖、自我依赖等）
        return web.json_response(
            {"error": str(e)},
            status=400
        )
    except FileNotFoundError:
        return web.json_response(
            {"error": f"Board '{board_slug}' not found"},
            status=404
        )
    except Exception as e:
        return web.json_response(
            {"error": f"Internal error: {str(e)}"},
            status=500
        )


async def unlink_tasks(request: web.Request) -> web.Response:
    """Remove a dependency link"""
    board_slug = request.match_info["board"]
    task_id = request.match_info["task_id"]

    try:
        data = await request.json()
        parent_id = data.get("parent_id")

        if not parent_id:
            return web.json_response(
                {"error": "Missing required field: parent_id"},
                status=400
            )

        from hermes_cli import kanban_db

        conn = kanban_db.connect(board=board_slug)
        try:
            # 检查任务是否存在
            parent_task = kanban_db.get_task(conn, parent_id)
            child_task = kanban_db.get_task(conn, task_id)

            if not parent_task:
                return web.json_response(
                    {"error": f"Parent task '{parent_id}' not found"},
                    status=404
                )

            if not child_task:
                return web.json_response(
                    {"error": f"Child task '{task_id}' not found"},
                    status=404
                )

            # 删除依赖关系
            kanban_db.unlink_tasks(conn, parent_id, task_id)

            return web.json_response({
                "message": f"Unlinked {parent_id} → {task_id}",
                "parent": {
                    "id": parent_task.id,
                    "title": parent_task.title
                },
                "child": {
                    "id": child_task.id,
                    "title": child_task.title
                }
            })
        finally:
            conn.close()

    except FileNotFoundError:
        return web.json_response(
            {"error": f"Board '{board_slug}' not found"},
            status=404
        )
    except Exception as e:
        return web.json_response(
            {"error": f"Internal error: {str(e)}"},
            status=500
        )


async def get_parents(request: web.Request) -> web.Response:
    """Get parent tasks (dependencies)"""
    board_slug = request.match_info["board"]
    task_id = request.match_info["task_id"]

    try:
        from hermes_cli import kanban_db

        conn = kanban_db.connect(board=board_slug)
        try:
            parent_ids_list = kanban_db.parent_ids(conn, task_id)

            parents = []
            for pid in parent_ids_list:
                task = kanban_db.get_task(conn, pid)
                if task:
                    parents.append({"id": task.id, "title": task.title, "status": task.status})

            return web.json_response({
                "task_id": task_id,
                "parents": parents
            })
        finally:
            conn.close()

    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def get_children(request: web.Request) -> web.Response:
    """Get child tasks (dependents)"""
    board_slug = request.match_info["board"]
    task_id = request.match_info["task_id"]

    try:
        from hermes_cli import kanban_db

        conn = kanban_db.connect(board=board_slug)
        try:
            child_ids_list = kanban_db.child_ids(conn, task_id)

            children = []
            for cid in child_ids_list:
                task = kanban_db.get_task(conn, cid)
                if task:
                    children.append({"id": task.id, "title": task.title, "status": task.status})

            return web.json_response({
                "task_id": task_id,
                "children": children
            })
        finally:
            conn.close()

    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def get_task_conversation(request: web.Request) -> web.Response:
    """
    Get conversation history for a task.

    Returns:
        200 with messages array
    """
    board_slug = request.match_info["board"]
    task_id = request.match_info["task_id"]

    try:
        from hermes_cli import kanban_db
        import sqlite3
        from pathlib import Path

        # Get task to retrieve session_id
        conn = kanban_db.connect(board=board_slug)
        try:
            task = kanban_db.get_task(conn, task_id)

            if not task:
                return web.json_response(
                    {"error": f"Task '{task_id}' not found"},
                    status=404
                )

            if not task.session_id:
                return web.json_response({
                    "task_id": task_id,
                    "session_id": None,
                    "messages": [],
                    "message": "Task has no associated session"
                })

            # Connect to state database to get messages
            state_db_path = Path.home() / ".hermes" / "state.db"
            if not state_db_path.exists():
                return web.json_response({
                    "task_id": task_id,
                    "session_id": task.session_id,
                    "messages": [],
                    "message": "State database not found"
                })

            state_conn = sqlite3.connect(str(state_db_path))
            state_conn.row_factory = sqlite3.Row

            try:
                cursor = state_conn.execute(
                    """
                    SELECT
                        id, role, content, tool_call_id, tool_calls, tool_name,
                        timestamp, token_count, finish_reason, reasoning
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY timestamp ASC
                    """,
                    (task.session_id,)
                )

                messages = []
                for row in cursor.fetchall():
                    msg = {
                        "id": row["id"],
                        "role": row["role"],
                        "content": row["content"],
                        "timestamp": row["timestamp"],
                        "token_count": row["token_count"],
                        "finish_reason": row["finish_reason"]
                    }

                    # Add optional fields if present
                    if row["tool_call_id"]:
                        msg["tool_call_id"] = row["tool_call_id"]
                    if row["tool_calls"]:
                        import json
                        try:
                            msg["tool_calls"] = json.loads(row["tool_calls"])
                        except:
                            msg["tool_calls"] = row["tool_calls"]
                    if row["tool_name"]:
                        msg["tool_name"] = row["tool_name"]
                    if row["reasoning"]:
                        msg["reasoning"] = row["reasoning"]

                    messages.append(msg)

                return web.json_response({
                    "task_id": task_id,
                    "session_id": task.session_id,
                    "message_count": len(messages),
                    "messages": messages
                })

            finally:
                state_conn.close()

        finally:
            conn.close()

    except FileNotFoundError:
        return web.json_response(
            {"error": f"Board '{board_slug}' not found"},
            status=404
        )
    except Exception as e:
        return web.json_response(
            {"error": str(e)},
            status=500
        )


async def get_task_conversation_summary(request: web.Request) -> web.Response:
    """
    Get a summary of task conversation (user messages only).

    Returns:
        200 with simplified message list
    """
    board_slug = request.match_info["board"]
    task_id = request.match_info["task_id"]

    try:
        from hermes_cli import kanban_db
        import sqlite3
        from pathlib import Path

        # Get task to retrieve session_id
        conn = kanban_db.connect(board=board_slug)
        try:
            task = kanban_db.get_task(conn, task_id)

            if not task:
                return web.json_response(
                    {"error": f"Task '{task_id}' not found"},
                    status=404
                )

            if not task.session_id:
                return web.json_response({
                    "task_id": task_id,
                    "session_id": None,
                    "summary": "No conversation - task not started"
                })

            # Connect to state database
            state_db_path = Path.home() / ".hermes" / "state.db"
            if not state_db_path.exists():
                return web.json_response({
                    "task_id": task_id,
                    "session_id": task.session_id,
                    "summary": "State database not found"
                })

            state_conn = sqlite3.connect(str(state_db_path))
            state_conn.row_factory = sqlite3.Row

            try:
                # Get user and assistant messages only (skip tool calls)
                cursor = state_conn.execute(
                    """
                    SELECT role, content, timestamp
                    FROM messages
                    WHERE session_id = ? AND role IN ('user', 'assistant')
                    ORDER BY timestamp ASC
                    """,
                    (task.session_id,)
                )

                messages = []
                for row in cursor.fetchall():
                    messages.append({
                        "role": row["role"],
                        "content": row["content"][:200] if row["content"] else "",  # Truncate long content
                        "timestamp": row["timestamp"]
                    })

                return web.json_response({
                    "task_id": task_id,
                    "task_title": task.title,
                    "session_id": task.session_id,
                    "message_count": len(messages),
                    "messages": messages
                })

            finally:
                state_conn.close()

        finally:
            conn.close()

    except FileNotFoundError:
        return web.json_response(
            {"error": f"Board '{board_slug}' not found"},
            status=404
        )
    except Exception as e:
        return web.json_response(
            {"error": str(e)},
            status=500
        )


async def get_task_events(request: web.Request) -> web.Response:
    """
    GET /v1/boards/{board}/tasks/{task_id}/events

    返回任务的事件流水（claimed/spawned/heartbeat/completed 等）。

    Query params:
        limit: 返回条数，默认 50
        since: 只返回 created_at > since 的事件（Unix 时间戳，用于轮询增量）
    """
    board_slug = request.match_info["board"]
    task_id = request.match_info["task_id"]
    limit = int(request.rel_url.query.get("limit", 50))
    since = request.rel_url.query.get("since")

    try:
        from hermes_cli import kanban_db

        conn = kanban_db.connect(board=board_slug)
        try:
            task = kanban_db.get_task(conn, task_id)
            if not task:
                return web.json_response({"error": f"Task '{task_id}' not found"}, status=404)

            if since:
                rows = conn.execute(
                    "SELECT id, task_id, run_id, kind, payload, created_at "
                    "FROM task_events WHERE task_id = ? AND created_at > ? "
                    "ORDER BY created_at ASC LIMIT ?",
                    (task_id, int(since), limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, task_id, run_id, kind, payload, created_at "
                    "FROM task_events WHERE task_id = ? "
                    "ORDER BY created_at ASC LIMIT ?",
                    (task_id, limit),
                ).fetchall()

            events = []
            for row in rows:
                payload = None
                if row["payload"]:
                    try:
                        payload = json.loads(row["payload"])
                    except Exception:
                        payload = row["payload"]
                events.append({
                    "id": row["id"],
                    "run_id": row["run_id"],
                    "kind": row["kind"],
                    "payload": payload,
                    "created_at": row["created_at"],
                })

            return web.json_response({
                "task_id": task_id,
                "task_title": task.title,
                "task_status": task.status,
                "event_count": len(events),
                "events": events,
            })

        finally:
            conn.close()

    except FileNotFoundError:
        return web.json_response({"error": f"Board '{board_slug}' not found"}, status=404)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def get_task_runs(request: web.Request) -> web.Response:
    """
    GET /v1/boards/{board}/tasks/{task_id}/runs

    返回任务的每次运行记录（开始时间、结束时间、结果摘要、错误信息等）。

    Query params:
        include_steps: true — 同时返回每次 run 的工具调用步骤流水（类似 Claude Code 展示方式）
        latest: true — 只返回最新一次 run
    """
    board_slug = request.match_info["board"]
    task_id = request.match_info["task_id"]
    include_steps = request.rel_url.query.get("include_steps", "").lower() == "true"
    latest_only = request.rel_url.query.get("latest", "").lower() == "true"

    try:
        import sqlite3 as _sqlite3
        from pathlib import Path
        from hermes_cli import kanban_db

        conn = kanban_db.connect(board=board_slug)
        try:
            task = kanban_db.get_task(conn, task_id)
            if not task:
                return web.json_response({"error": f"Task '{task_id}' not found"}, status=404)

            query = (
                "SELECT id, profile, step_key, status, claim_lock, worker_pid, "
                "started_at, ended_at, outcome, summary, error, metadata "
                "FROM task_runs WHERE task_id = ? ORDER BY started_at ASC"
            )
            rows = conn.execute(query, (task_id,)).fetchall()

        finally:
            conn.close()

        if latest_only and rows:
            rows = [rows[-1]]

        # 如果需要工具调用步骤，按 profile 查找对应的 state.db
        # gateway 每个 profile 有独立的 state.db：~/.hermes/profiles/{profile}/state.db
        # 全局 gateway 用 ~/.hermes/state.db
        def _get_state_conn(profile: str):
            hermes_home = Path.home() / ".hermes"
            candidates = [
                hermes_home / "profiles" / profile / "state.db",
                hermes_home / "state.db",
            ]
            for p in candidates:
                if p.exists():
                    c = _sqlite3.connect(str(p))
                    c.row_factory = _sqlite3.Row
                    return c
            return None

        state_conn = None  # 占位，按 run 的 profile 动态打开

        runs = []
        for row in rows:
                metadata = None
                if row["metadata"]:
                    try:
                        metadata = json.loads(row["metadata"])
                    except Exception:
                        metadata = row["metadata"]

                duration = None
                if row["started_at"] and row["ended_at"]:
                    duration = row["ended_at"] - row["started_at"]

                run_entry = {
                    "id": row["id"],
                    "profile": row["profile"],
                    "step_key": row["step_key"],
                    "status": row["status"],
                    "claim_lock": row["claim_lock"],
                    "worker_pid": row["worker_pid"],
                    "started_at": row["started_at"],
                    "ended_at": row["ended_at"],
                    "duration_seconds": duration,
                    "outcome": row["outcome"],
                    "summary": row["summary"],
                    "error": row["error"],
                    "metadata": metadata,
                }

                # 从对应 profile 的 state.db 加载工具调用步骤
                if include_steps and metadata:
                    run_profile = row["profile"] or ""
                    state_conn = _get_state_conn(run_profile)
                    session_id = metadata.get("worker_session_id", "")
                    if session_id and state_conn:
                        msg_rows = state_conn.execute(
                            """
                            SELECT role, tool_name, tool_call_id, content, tool_calls, timestamp
                            FROM messages
                            WHERE session_id = ?
                            ORDER BY timestamp ASC
                            """,
                            (session_id,),
                        ).fetchall()

                        steps = []
                        for msg in msg_rows:
                            tool_calls = None
                            if msg["tool_calls"]:
                                try:
                                    tool_calls = json.loads(msg["tool_calls"])
                                except Exception:
                                    pass

                            step = {
                                "role": msg["role"],
                                "timestamp": msg["timestamp"],
                            }

                            if msg["role"] == "assistant":
                                # assistant 消息：提取文字内容和工具调用列表
                                step["content"] = msg["content"] or ""
                                if tool_calls:
                                    step["tool_calls"] = [
                                        {
                                            "id": tc.get("id"),
                                            "name": tc.get("function", {}).get("name"),
                                            "input": _safe_json(tc.get("function", {}).get("arguments")),
                                        }
                                        for tc in tool_calls
                                        if isinstance(tc, dict)
                                    ]
                            elif msg["role"] == "tool":
                                # 工具返回结果
                                step["tool_name"] = msg["tool_name"]
                                step["tool_call_id"] = msg["tool_call_id"]
                                raw = msg["content"] or ""
                                # 尝试解析 JSON 结果，截断过长内容
                                try:
                                    parsed = json.loads(raw)
                                    step["result"] = parsed
                                except Exception:
                                    step["result"] = raw[:500] if len(raw) > 500 else raw
                            elif msg["role"] == "user":
                                step["content"] = (msg["content"] or "")[:200]

                            steps.append(step)

                        run_entry["session_id"] = session_id
                        run_entry["steps"] = steps
                        run_entry["step_count"] = len(steps)
                        run_entry["tool_count"] = sum(1 for s in steps if s["role"] == "tool")

                    if state_conn:
                        state_conn.close()
                        state_conn = None

                runs.append(run_entry)

        return web.json_response({
            "task_id": task_id,
            "task_title": task.title,
            "task_status": task.status,
            "run_count": len(runs),
            "runs": runs,
        })

    except FileNotFoundError:
        return web.json_response({"error": f"Board '{board_slug}' not found"}, status=404)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def get_task_thread_messages(request: web.Request) -> web.Response:
    """
    GET /v1/boards/{board}/tasks/{task_id}/thread-messages

    以主任务为根，递归收集自身及所有子任务产生的消息，去重后按时间排序返回。

    返回格式:
        {
          "task_id": "t_xxx",
          "task_title": "主任务名",
          "messages": [
            {
              "task_id": "t_xxx",
              "task_title": "任务名称",
              "role": "user" | "assistant",
              "content": "消息内容",
              "timestamp": 1234567890.0
            },
            ...
          ],
          "task_count": 3,
          "message_count": 10
        }

    Query params:
        roles: 过滤角色，逗号分隔，默认 "assistant"（只返回 AI 回复）
               传 "all" 返回 user+assistant
    """
    board_slug = request.match_info["board"]
    task_id = request.match_info["task_id"]
    roles_param = request.rel_url.query.get("roles", "assistant")
    if roles_param == "all":
        allowed_roles = {"user", "assistant"}
    else:
        allowed_roles = {r.strip() for r in roles_param.split(",")}

    try:
        import sqlite3 as _sqlite3
        from pathlib import Path
        from hermes_cli import kanban_db

        conn = kanban_db.connect(board=board_slug)
        try:
            root_task = kanban_db.get_task(conn, task_id)
            if not root_task:
                return web.json_response({"error": f"Task '{task_id}' not found"}, status=404)

            # 递归收集主任务及所有子任务（BFS）
            visited = {}  # task_id -> title
            queue = [task_id]
            while queue:
                current_id = queue.pop(0)
                if current_id in visited:
                    continue
                t = kanban_db.get_task(conn, current_id)
                if not t:
                    continue
                visited[current_id] = t.title
                child_ids = kanban_db.child_ids(conn, current_id)
                for cid in child_ids:
                    if cid not in visited:
                        queue.append(cid)

        finally:
            conn.close()

        # 从 state.db 按 kanban_{task_id}_% 前缀匹配消息
        state_db_path = Path.home() / ".hermes" / "state.db"
        if not state_db_path.exists():
            return web.json_response({
                "task_id": task_id,
                "task_title": root_task.title,
                "messages": [],
                "task_count": len(visited),
                "message_count": 0,
            })

        all_messages = []
        seen_content = set()  # 用于去重

        # 重新连接 board db 查 task_runs（conn 已关闭，重开一个只读查询）
        conn2 = kanban_db.connect(board=board_slug)
        try:
            # 收集每个任务最新一次成功 run 的 summary 和 started_at，作为 fallback
            task_run_fallback = {}  # tid -> {"summary": str, "started_at": int}
            for tid in visited:
                run = conn2.execute(
                    "SELECT summary, started_at FROM task_runs "
                    "WHERE task_id = ? AND status = 'done' AND summary IS NOT NULL AND summary != '' "
                    "ORDER BY started_at DESC LIMIT 1",
                    (tid,),
                ).fetchone()
                if run:
                    task_run_fallback[tid] = {
                        "summary": run["summary"],
                        "started_at": run["started_at"],
                    }
        finally:
            conn2.close()

        # 优先从 state.db 取完整对话消息
        state_db_path = Path.home() / ".hermes" / "state.db"
        if state_db_path.exists():
            state_conn = _sqlite3.connect(str(state_db_path))
            state_conn.row_factory = _sqlite3.Row
            try:
                for tid, title in visited.items():
                    prefix = f"kanban_{tid}_%"
                    rows = state_conn.execute(
                        """
                        SELECT session_id, role, content, timestamp
                        FROM messages
                        WHERE session_id LIKE ? AND role IN ({})
                        ORDER BY timestamp ASC
                        """.format(",".join("?" * len(allowed_roles))),
                        (prefix, *allowed_roles),
                    ).fetchall()

                    if not rows:
                        continue

                    # 只取最新 session
                    sessions = {}
                    for row in rows:
                        sid = row["session_id"]
                        if sid not in sessions:
                            sessions[sid] = []
                        sessions[sid].append(row)

                    latest_session = max(sessions.keys())
                    # 最新 session 的时间戳（session_id 末尾数字）
                    try:
                        latest_ts = int(latest_session.rsplit("_", 1)[-1])
                    except ValueError:
                        latest_ts = 0

                    # 如果 task_runs 里有更新的执行结果，跳过 state.db（用 fallback）
                    fallback = task_run_fallback.get(tid)
                    if fallback and fallback["started_at"] > latest_ts:
                        continue  # 走 fallback 分支

                    for row in sessions[latest_session]:
                        content = row["content"] or ""
                        dedup_key = content.strip()[:200]
                        if dedup_key in seen_content:
                            continue
                        seen_content.add(dedup_key)
                        all_messages.append({
                            "task_id": tid,
                            "task_title": title,
                            "role": row["role"],
                            "content": content,
                            "timestamp": row["timestamp"],
                        })
                        # 标记该任务已有消息，不走 fallback
                        task_run_fallback.pop(tid, None)
            finally:
                state_conn.close()

        # fallback：state.db 无消息的任务，用 task_runs.summary 补充
        if "assistant" in allowed_roles:
            for tid, title in visited.items():
                fallback = task_run_fallback.get(tid)
                if not fallback:
                    continue
                content = fallback["summary"]
                dedup_key = content.strip()[:200]
                if dedup_key in seen_content:
                    continue
                seen_content.add(dedup_key)
                all_messages.append({
                    "task_id": tid,
                    "task_title": title,
                    "role": "assistant",
                    "content": content,
                    "timestamp": float(fallback["started_at"]),
                })

        # 按时间排序
        all_messages.sort(key=lambda m: m["timestamp"])

        return web.json_response({
            "task_id": task_id,
            "task_title": root_task.title,
            "messages": all_messages,
            "task_count": len(visited),
            "message_count": len(all_messages),
        })

    except FileNotFoundError:
        return web.json_response({"error": f"Board '{board_slug}' not found"}, status=404)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
