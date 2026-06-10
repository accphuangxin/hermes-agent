"""Database connection helper with automatic cleanup"""
from contextlib import contextmanager
from typing import Generator
import sqlite3


@contextmanager
def get_board_connection(board_slug: str) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for board database connections.
    Automatically closes the connection when done.

    Usage:
        with get_board_connection("my-board") as conn:
            tasks = kanban_db.list_tasks(conn)
            # conn automatically closed after this block
    """
    from hermes_cli import kanban_db

    conn = kanban_db.connect(board=board_slug)
    try:
        yield conn
    finally:
        conn.close()
