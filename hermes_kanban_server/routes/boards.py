"""Board management endpoints"""

import json
import time
import asyncio
from pathlib import Path
from aiohttp import web


async def create_board(request: web.Request) -> web.Response:
    """
    Create a new Kanban board.

    Request body:
        {
            "slug": "board-name",
            "name": "Display Name",
            "description": "Optional description",
            "icon": "🏥",
            "color": "#10b981"
        }

    Returns:
        201 with created board info
    """
    try:
        data = await request.json()

        slug = data.get("slug")
        name = data.get("name", slug)
        description = data.get("description", "")
        icon = data.get("icon", "📋")
        color = data.get("color", "#3b82f6")

        if not slug:
            return web.json_response(
                {"error": "Missing required field: slug"},
                status=400
            )

        # Create board directory
        boards_root = Path.home() / ".hermes" / "kanban" / "boards"
        board_dir = boards_root / slug

        if board_dir.exists():
            return web.json_response(
                {"error": f"Board '{slug}' already exists"},
                status=409
            )

        board_dir.mkdir(parents=True, exist_ok=True)

        # Create board metadata file
        board_meta = {
            "slug": slug,
            "displayName": name,
            "description": description,
            "icon": icon,
            "color": color,
            "createdAt": time.time(),
        }

        meta_path = board_dir / "board.json"
        meta_path.write_text(json.dumps(board_meta, indent=2, ensure_ascii=False), encoding="utf-8")

        # Initialize board database
        from hermes_cli import kanban_db
        kanban_db.init_db(board=slug)

        return web.json_response(board_meta, status=201)

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


async def list_boards(request: web.Request) -> web.Response:
    """
    List all available Kanban boards.

    Returns:
        JSON array of board metadata
    """
    try:
        boards_root = Path.home() / ".hermes" / "kanban" / "boards"
        boards = []

        if boards_root.exists():
            for board_dir in boards_root.iterdir():
                if board_dir.is_dir():
                    meta_path = board_dir / "board.json"
                    if meta_path.exists():
                        try:
                            board_meta = json.loads(meta_path.read_text(encoding="utf-8"))
                            boards.append(board_meta)
                        except Exception:
                            # Skip boards with corrupted metadata
                            pass

        # Also check for default board (backward compatibility)
        default_db = Path.home() / ".hermes" / "kanban.db"
        if default_db.exists():
            # Check if "default" board is already in list
            if not any(b["slug"] == "default" for b in boards):
                boards.append({
                    "slug": "default",
                    "displayName": "Default",
                    "description": "Default Kanban board",
                    "icon": "📋",
                    "color": "#3b82f6",
                })

        return web.json_response({"boards": boards})

    except Exception as e:
        return web.json_response(
            {"error": str(e)},
            status=500
        )


async def get_board(request: web.Request) -> web.Response:
    """
    Get board metadata and statistics.

    Args:
        request: Must contain {slug} in match_info

    Returns:
        JSON with board info and task statistics
    """
    slug = request.match_info["slug"]

    try:
        boards_root = Path.home() / ".hermes" / "kanban" / "boards"
        board_dir = boards_root / slug
        meta_path = board_dir / "board.json"

        if not meta_path.exists():
            # Check for default board
            if slug == "default" and (Path.home() / ".hermes" / "kanban.db").exists():
                board_meta = {
                    "slug": "default",
                    "displayName": "Default",
                    "description": "Default Kanban board",
                    "icon": "📋",
                    "color": "#3b82f6",
                }
            else:
                return web.json_response(
                    {"error": f"Board '{slug}' not found"},
                    status=404
                )
        else:
            board_meta = json.loads(meta_path.read_text(encoding="utf-8"))

        # Add task statistics
        from hermes_cli import kanban_db
        conn = kanban_db.connect(board=slug)
        try:
            tasks = kanban_db.list_tasks(conn)

            board_meta["taskCount"] = len(tasks)
            board_meta["statusCounts"] = {}

            for task in tasks:
                status = task.status
                board_meta["statusCounts"][status] = board_meta["statusCounts"].get(status, 0) + 1

            return web.json_response(board_meta)
        finally:
            conn.close()

    except FileNotFoundError:
        return web.json_response(
            {"error": f"Board '{slug}' not found"},
            status=404
        )
    except Exception as e:
        return web.json_response(
            {"error": str(e)},
            status=500
        )


async def update_board(request: web.Request) -> web.Response:
    """
    Update board metadata.

    Args:
        request: Must contain {slug} in match_info

    Request body:
        {
            "name": "New Display Name",
            "description": "New description",
            "icon": "🎯",
            "color": "#ef4444"
        }

    Returns:
        200 with updated board info
    """
    slug = request.match_info["slug"]

    try:
        data = await request.json()

        boards_root = Path.home() / ".hermes" / "kanban" / "boards"
        board_dir = boards_root / slug
        meta_path = board_dir / "board.json"

        if not meta_path.exists():
            return web.json_response(
                {"error": f"Board '{slug}' not found"},
                status=404
            )

        board_meta = json.loads(meta_path.read_text(encoding="utf-8"))

        # Update fields
        if "name" in data:
            board_meta["displayName"] = data["name"]
        if "description" in data:
            board_meta["description"] = data["description"]
        if "icon" in data:
            board_meta["icon"] = data["icon"]
        if "color" in data:
            board_meta["color"] = data["color"]

        board_meta["updatedAt"] = time.time()

        # Save updated metadata
        meta_path.write_text(json.dumps(board_meta, indent=2, ensure_ascii=False), encoding="utf-8")

        return web.json_response(board_meta)

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


async def delete_board(request: web.Request) -> web.Response:
    """
    Delete a board and all its data.

    Args:
        request: Must contain {slug} in match_info

    Returns:
        204 No Content on success
    """
    slug = request.match_info["slug"]

    try:
        import shutil

        boards_root = Path.home() / ".hermes" / "kanban" / "boards"
        board_dir = boards_root / slug

        if not board_dir.exists():
            return web.json_response(
                {"error": f"Board '{slug}' not found"},
                status=404
            )

        # Delete entire board directory
        shutil.rmtree(board_dir)

        return web.Response(status=204)

    except Exception as e:
        return web.json_response(
            {"error": str(e)},
            status=500
        )


async def init_board(request: web.Request) -> web.Response:
    """
    Initialize or reinitialize board database schema.

    Args:
        request: Must contain {slug} in match_info

    Returns:
        200 with confirmation message
    """
    slug = request.match_info["slug"]

    try:
        from hermes_cli import kanban_db

        kanban_db.init_db(board=slug)

        return web.json_response({
            "message": f"Board '{slug}' database initialized successfully"
        })

    except Exception as e:
        return web.json_response(
            {"error": str(e)},
            status=500
        )


async def trigger_board(request: web.Request) -> web.Response:
    """
    Trigger daemon to process tasks on a board.

    Request body (optional):
        {
            "assignee": "agent-name",      # Optional: only process this assignee's tasks
            "task_id": "t_xxx",            # Optional: only process this specific task
            "title": "任务标题",            # Optional: filter by title (contains match)
            "include_children": true,       # Optional: include all child tasks (default: true)
            "max_tasks": 10,                # Optional: limit number of tasks to process
            "once": true,                   # Optional: run once instead of continuous (default: true)
            "initial_prompt": "开始分析..."  # Optional: initial message to start conversation
        }

    Returns:
        200 with processing results
    """
    board_slug = request.match_info["board"]

    try:
        # Parse request body (all fields optional)
        try:
            data = await request.json()
        except:
            data = {}

        assignee = data.get("assignee")
        task_id = data.get("task_id")
        title_filter = data.get("title")
        include_children = data.get("include_children", True)  # 默认包含子任务
        max_tasks = data.get("max_tasks", 10)
        once = data.get("once", True)
        initial_prompt = data.get("initial_prompt")
        loop_count = int(data.get("loop_count", 0))  # 0=不循环, N=循环N次, -1=无限循环

        from hermes_cli import kanban_db
        from pathlib import Path

        # Check board exists
        boards_root = Path.home() / ".hermes" / "kanban" / "boards"
        board_dir = boards_root / board_slug
        if not board_dir.exists():
            return web.json_response(
                {"error": f"Board '{board_slug}' not found"},
                status=404
            )

        conn = kanban_db.connect(board=board_slug)
        try:
            # 清理孤儿任务：running 状态但 claim_lock 里的 PID 已不存在
            import os
            import time as _time
            stale_running = conn.execute(
                "SELECT id, claim_lock FROM tasks WHERE status = 'running'"
            ).fetchall()
            for row in stale_running:
                claim_lock = row["claim_lock"] or ""
                # claim_lock 格式: "hostname:pid"
                pid = None
                if ":" in claim_lock:
                    try:
                        pid = int(claim_lock.split(":")[-1])
                    except ValueError:
                        pass
                is_dead = True
                if pid:
                    try:
                        os.kill(pid, 0)  # 不发信号，只检查进程是否存在
                        is_dead = False
                    except (ProcessLookupError, PermissionError):
                        is_dead = True
                if is_dead:
                    conn.execute(
                        "UPDATE tasks SET status = 'ready', claim_lock = NULL, "
                        "claim_expires = NULL, started_at = NULL WHERE id = ?",
                        (row["id"],),
                    )
            conn.commit()

            # Get ready tasks
            all_ready_tasks = kanban_db.list_tasks(conn, status="ready")

            # Filter out tasks whose parent tasks are not completed
            # 过滤掉父任务未完成的任务
            def can_execute(task):
                """检查任务是否可以执行（所有父任务都已完成）"""
                parent_ids = kanban_db.parent_ids(conn, task.id)
                if not parent_ids:
                    return True  # 没有依赖，可以执行

                for parent_id in parent_ids:
                    parent = kanban_db.get_task(conn, parent_id)
                    if not parent or parent.status != "done":
                        return False  # 父任务未完成

                return True  # 所有父任务都完成

            # 只保留依赖已满足的任务
            all_tasks = [t for t in all_ready_tasks if can_execute(t)]

            # Filter by task_id if specified (exact match)
            if task_id:
                tasks_to_process = [t for t in all_tasks if t.id == task_id]
            # Filter by title if specified (contains match, case-insensitive)
            elif title_filter:
                tasks_to_process = [t for t in all_tasks if title_filter.lower() in t.title.lower()]
            # Filter by assignee if specified
            elif assignee:
                tasks_to_process = [t for t in all_tasks if t.assignee == assignee]
            else:
                tasks_to_process = all_tasks

            # 注意：如果 include_children=True，我们不在这里展开子任务
            # 而是在执行过程中，每执行完一个任务，就检查并执行其子任务
            # 这样可以确保子任务在父任务完成后才执行，并能接收到父任务的结果

            # Apply max_tasks limit
            tasks_to_process = tasks_to_process[:max_tasks]

            if not tasks_to_process:
                return web.json_response({
                    "message": "No ready tasks to process",
                    "board": board_slug,
                    "processed": 0,
                    "filters": {
                        "assignee": assignee,
                        "task_id": task_id,
                        "title": title_filter
                    }
                })

            # Process tasks in dependency order
            processed_count = 0
            processed_tasks = []
            errors = []

            # Import task executor
            from hermes_kanban_server.task_executor import execute_task

            # Build dependency graph
            def get_execution_order(tasks):
                """
                返回按依赖顺序排列的任务列表（拓扑排序）
                父任务必须在子任务之前执行
                """
                from collections import defaultdict, deque

                task_map = {t.id: t for t in tasks}
                task_ids = set(t.id for t in tasks)

                # 构建邻接表和入度表（只考虑当前要执行的任务）
                graph = defaultdict(list)  # parent -> [children]
                in_degree = {tid: 0 for tid in task_ids}

                for task_id in task_ids:
                    parent_ids = kanban_db.parent_ids(conn, task_id)
                    # 只考虑在当前任务集合中的父任务
                    relevant_parents = [pid for pid in parent_ids if pid in task_ids]
                    in_degree[task_id] = len(relevant_parents)

                    for parent_id in relevant_parents:
                        graph[parent_id].append(task_id)

                # 拓扑排序（Kahn算法）
                queue = deque([tid for tid in task_ids if in_degree[tid] == 0])
                result = []

                while queue:
                    current_id = queue.popleft()
                    result.append(task_map[current_id])

                    # 处理子任务
                    for child_id in graph[current_id]:
                        in_degree[child_id] -= 1
                        if in_degree[child_id] == 0:
                            queue.append(child_id)

                # 如果有循环依赖，剩余的任务按原顺序添加
                if len(result) < len(tasks):
                    remaining = [t for t in tasks if t not in result]
                    result.extend(remaining)

                return result

            # 按依赖顺序执行任务
            ordered_tasks = get_execution_order(tasks_to_process)

            # 用于跟踪已执行的任务
            executed_task_ids = set()

            async def execute_task_with_children(task):
                """执行任务，并在完成后递归执行其子任务"""
                if task.id in executed_task_ids:
                    return  # 已执行过

                try:
                    # Prepare task body
                    task_body = task.body or ""

                    # If initial_prompt provided, append it to task body
                    if initial_prompt:
                        separator = "\n\n---\n\n**初始提示：**\n" if task_body else "**初始提示：**\n"
                        task_body = task_body + separator + initial_prompt

                        # Update task body in database
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE tasks SET body = ? WHERE id = ?",
                            (task_body, task.id)
                        )
                        conn.commit()

                    # Claim the task
                    claimed = kanban_db.claim_task(conn, task.id)
                    if not claimed:
                        return

                    # Execute task (creates session, calls agent, records conversation)
                    # execute_task 内部会自动获取父任务结果并传递
                    execution_result = await execute_task(
                        board=board_slug,
                        task_id=task.id,
                        task_body=task_body,
                        assignee=task.assignee
                    )

                    executed_task_ids.add(task.id)

                    if execution_result["success"]:
                        nonlocal processed_count
                        processed_count += 1
                        processed_tasks.append({
                            "id": task.id,
                            "title": task.title,
                            "status": execution_result["status"],
                            "session_id": execution_result["session_id"],
                            "message_count": execution_result.get("message_count", 0),
                            "initial_prompt_added": bool(initial_prompt)
                        })

                        # 如果 include_children=True，并行执行所有子任务
                        if include_children:
                            child_ids = kanban_db.child_ids(conn, task.id)
                            child_tasks = []
                            for child_id in child_ids:
                                child_task = kanban_db.get_task(conn, child_id)
                                if child_task and child_task.status == "ready":
                                    child_tasks.append(child_task)

                            # 并行执行所有子任务
                            if child_tasks:
                                import asyncio
                                await asyncio.gather(*[
                                    execute_task_with_children(ct) for ct in child_tasks
                                ])

                    else:
                        errors.append({
                            "task_id": task.id,
                            "error": execution_result.get("error", "Unknown error")
                        })

                except Exception as e:
                    errors.append({
                        "task_id": task.id,
                        "error": str(e)
                    })

            # 执行所有根任务（会递归执行子任务）
            for task in ordered_tasks:
                await execute_task_with_children(task)

            # 循环执行：每轮结束后重置任务，重新触发
            loop_results = []
            current_loop = 0

            while loop_count != 0:
                # 收集本轮参与的任务 ID（主任务 + 所有子孙）
                all_task_ids = list(executed_task_ids)

                # 重置：先重置叶子任务，再重置根任务（保证依赖顺序正确）
                conn2 = kanban_db.connect(board=board_slug)
                try:
                    reset_sql = """
                        UPDATE tasks
                        SET status = 'todo',
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
                    cursor2 = conn2.cursor()
                    for tid in all_task_ids:
                        cursor2.execute(reset_sql, (tid,))
                    conn2.commit()

                    # recompute_ready 将根任务（无父任务）晋级为 ready
                    kanban_db.recompute_ready(conn2)
                finally:
                    conn2.close()

                loop_results.append({
                    "loop": current_loop + 1,
                    "processed": processed_count,
                    "errors": len(errors),
                })
                current_loop += 1
                if loop_count > 0 and current_loop >= loop_count:
                    break

                # 重新加载 ready 任务并执行
                processed_count = 0
                processed_tasks = []
                errors = []
                executed_task_ids = set()

                conn3 = kanban_db.connect(board=board_slug)
                try:
                    next_ready = kanban_db.list_tasks(conn3, status="ready")
                    if task_id:
                        next_tasks = [t for t in next_ready if t.id == task_id]
                    else:
                        # recompute_ready 已确保只有无阻塞依赖的任务变 ready，直接用
                        next_tasks = next_ready
                    next_tasks = next_tasks[:max_tasks]
                finally:
                    conn3.close()

                for task in next_tasks:
                    await execute_task_with_children(task)

            response_data = {
                "message": f"Triggered processing for {processed_count} task(s)",
                "board": board_slug,
                "assignee": assignee,
                "processed": processed_count,
                "tasks": processed_tasks,
                "errors": errors if errors else None,
            }

            if loop_results:
                response_data["loops"] = loop_results
                response_data["total_loops"] = len(loop_results) + 1

            if initial_prompt:
                response_data["initial_prompt"] = initial_prompt

            return web.json_response(response_data)

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
