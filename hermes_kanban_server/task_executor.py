"""
Kanban Task Executor
在 trigger API 中同步/异步执行任务
"""
import asyncio
import sqlite3
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import time


async def execute_task(board: str, task_id: str, task_body: str,
                       assignee: str) -> Dict[str, Any]:
    """
    执行单个 Kanban 任务

    完整流程：
    1. 获取父任务结果（如果有依赖）
    2. 创建 session
    3. 调用 Agent（模拟/真实）
    4. 记录对话到 state.db
    5. 更新任务状态
    """
    import logging
    from hermes_cli import kanban_db

    logger = logging.getLogger(__name__)
    logger.info("="*80)
    logger.info(f"[EXECUTE_TASK] Starting: board={board}, task_id={task_id}, assignee={assignee}")
    logger.info("="*80)

    # 所有数据库操作在主线程中同步执行，避免 SQLite 跨线程问题
    conn = kanban_db.connect(board=board)
    try:
        # 1. 获取父任务结果
        logger.info("[STEP 1] Getting parent results...")
        parent_results = kanban_db.parent_results(conn, task_id)
        logger.info(f"[STEP 1] Got {len(parent_results)} parent results")

        # 2. 构建任务上下文
        full_context = _build_task_context(conn, task_body, parent_results)

        # 3. 创建 session_id 并更新到数据库
        session_id = f"kanban_{task_id}_{int(time.time())}"
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE tasks SET session_id = ? WHERE id = ?",
            (session_id, task_id)
        )
        conn.commit()
        logger.info(f"[STEP 3] Session created: {session_id}")

        # 4. 调用 Agent（异步）
        logger.info("[STEP 4] Calling agent...")
        result = await _call_agent(
            session_id=session_id,
            task_body=full_context,
            assignee=assignee
        )
        logger.info("[STEP 4] Agent call completed")

        # 5. 保存对话记录（异步）
        logger.info("[STEP 5] Saving conversation...")
        await _save_conversation(
            session_id=session_id,
            messages=result["messages"]
        )
        logger.info("[STEP 5] Conversation saved")

        # 6. 标记任务完成（同步，使用同一个 conn）
        logger.info("[STEP 6] Completing task in DB...")
        kanban_db.complete_task(
            conn=conn,
            task_id=task_id,
            result=result.get("summary", "Task completed")
        )
        logger.info("[STEP 6] Task completed")

        return {
            "success": True,
            "task_id": task_id,
            "session_id": session_id,
            "status": "done",
            "message_count": len(result["messages"])
        }

    except Exception as e:
        logger.error(f"[ERROR] Task execution failed: {e}", exc_info=True)
        try:
            kanban_db.fail_task(conn, task_id, str(e))
        except Exception as e2:
            logger.error(f"[ERROR] Failed to mark task as failed: {e2}")
        return {
            "success": False,
            "task_id": task_id,
            "session_id": locals().get("session_id"),
            "error": str(e)
        }

    finally:
        conn.close()


async def _get_profile_info(profile_name: str) -> Optional[Dict[str, Any]]:
    """从 agent-manager 获取 profile 信息"""
    import aiohttp
    import logging

    logger = logging.getLogger(__name__)

    try:
        logger.info(f"Fetching profile info for: {profile_name}")
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://127.0.0.1:8640/v1/agents",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    agents = data.get("agents", [])
                    for agent in agents:
                        if agent.get("name") == profile_name:
                            if agent.get("gatewayRunning"):
                                port = agent.get("apiServerPort")
                                logger.info(f"Profile '{profile_name}' found on port {port}")
                                return agent
                            else:
                                logger.warning(f"Profile '{profile_name}' gateway not running")
                                return None
                    logger.warning(f"Profile '{profile_name}' not found")
                    return None
                else:
                    logger.error(f"Failed to fetch agents: HTTP {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Failed to get profile info: {e}", exc_info=True)
        return None


def _build_task_context(conn: sqlite3.Connection, task_body: str,
                        parent_results: List[Tuple[str, Optional[str]]]) -> str:
    """构建任务的完整上下文（包含父任务结果）"""
    from hermes_cli import kanban_db

    if not parent_results:
        return task_body

    context_parts = ["**依赖任务的执行结果：**\n"]

    for parent_id, result in parent_results:
        try:
            parent_task = kanban_db.get_task(conn, parent_id)
            parent_title = parent_task.title if parent_task else parent_id
        except:
            parent_title = parent_id

        context_parts.append(f"\n### {parent_title}\n")
        context_parts.append(f"**任务ID:** {parent_id}\n")

        if result:
            context_parts.append(f"**执行结果:**\n{result}\n")
        else:
            context_parts.append("**执行结果:** （无返回结果）\n")

    context_parts.append("\n" + "="*60 + "\n\n")
    context_parts.append("**当前任务：**\n\n")
    context_parts.append(task_body)

    return "".join(context_parts)


async def _call_agent(session_id: str, task_body: str,
                      assignee: str) -> Dict[str, Any]:
    """调用 Agent 执行任务"""
    import aiohttp
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"Calling agent for session: {session_id}, assignee: {assignee}")

    profile_info = await _get_profile_info(assignee)

    if not profile_info:
        logger.warning(f"Profile '{assignee}' not available, using simulation")
        return await _simulate_execution(task_body, assignee)

    port = profile_info.get("apiServerPort")
    api_key = profile_info.get("apiServerKey", "")

    if not port:
        logger.warning(f"Profile '{assignee}' has no port configured, using simulation")
        return await _simulate_execution(task_body, assignee)

    agent_api_url = f"http://127.0.0.1:{port}/v1/chat/completions"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    logger.info(f"Calling agent API: {agent_api_url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                agent_api_url,
                json={
                    "model": "hermes-agent",
                    "messages": [
                        {"role": "user", "content": task_body}
                    ],
                    "stream": False
                },
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=300)
            ) as response:
                logger.info(f"Agent API response status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    assistant_msg = data["choices"][0]["message"]["content"]
                    logger.info(f"Agent responded with {len(assistant_msg)} chars")

                    return {
                        "messages": [
                            {
                                "role": "user",
                                "content": task_body,
                                "timestamp": time.time()
                            },
                            {
                                "role": "assistant",
                                "content": assistant_msg,
                                "timestamp": time.time() + 1
                            }
                        ],
                        "summary": assistant_msg[:200]
                    }
                else:
                    error_text = await response.text()
                    logger.error(f"Agent API error: {response.status} - {error_text}")
    except Exception as e:
        logger.error(f"Failed to call agent API: {e}", exc_info=True)

    return await _simulate_execution(task_body, assignee)


async def _simulate_execution(task_body: str, assignee: str) -> Dict[str, Any]:
    """模拟任务执行（当 Agent API 不可用时）"""
    await asyncio.sleep(0.5)

    assistant_response = f"""我是 {assignee}，已收到任务。

**任务内容：**
{task_body[:200]}

**执行结果：**
✅ 任务已处理完成。

由于真实 Agent API 未运行，这是模拟执行结果。
要获得真实执行，请启动 Agent Manager 或配置相应的 Agent API。
"""

    messages = [
        {
            "role": "user",
            "content": task_body,
            "timestamp": time.time()
        },
        {
            "role": "assistant",
            "content": assistant_response,
            "timestamp": time.time() + 1
        }
    ]

    return {
        "messages": messages,
        "summary": "任务已模拟执行完成"
    }


async def _save_conversation(session_id: str, messages: list):
    """保存对话记录到 state.db"""
    state_db_path = Path.home() / ".hermes" / "state.db"

    if not state_db_path.exists():
        _init_state_db(state_db_path)

    conn = sqlite3.connect(str(state_db_path))

    try:
        cursor = conn.cursor()

        for msg in messages:
            cursor.execute(
                """
                INSERT INTO messages
                (session_id, role, content, timestamp, token_count, finish_reason)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    msg["role"],
                    msg["content"],
                    msg["timestamp"],
                    msg.get("token_count"),
                    msg.get("finish_reason")
                )
            )

        conn.commit()
    finally:
        conn.close()


def _init_state_db(db_path: Path):
    """初始化 state.db（如果不存在）"""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))

    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                tool_call_id TEXT,
                tool_calls TEXT,
                tool_name TEXT,
                timestamp REAL NOT NULL,
                token_count INTEGER,
                finish_reason TEXT,
                reasoning TEXT,
                reasoning_content TEXT,
                reasoning_details TEXT,
                codex_reasoning_items TEXT,
                codex_message_items TEXT,
                platform_message_id TEXT,
                observed INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages(session_id)
        """)

        conn.commit()
    finally:
        conn.close()
