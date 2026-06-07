"""SQLite short-term message store — partitioned by chat_id."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path
from typing import Any


def _db_read(db_path: str, sql: str, params: tuple = ()) -> list:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(sql, params).fetchall()


def _db_write(db_path: str, sql: str, params: tuple = ()) -> int:
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid


class ShortTermMemory:
    """Short-term message storage with per-chat_id partitioning."""

    def __init__(self, data_dir: Path):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "short_term.db"
        self._consolidation_cursor: dict[str, int] = {}
        _db_write(
            str(self._db_path),
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL, user_id TEXT NOT NULL,
                role TEXT NOT NULL, content TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """,
        )
        _db_write(
            str(self._db_path),
            "CREATE INDEX IF NOT EXISTS idx_msg_ch ON messages(chat_id, created_at)",
        )

    async def add(self, chat_id: str, user_id: str, content: str, role: str = "user") -> None:
        await asyncio.to_thread(
            _db_write,
            str(self._db_path),
            "INSERT INTO messages (chat_id, user_id, role, content, created_at) VALUES (?,?,?,?,?)",
            (chat_id, user_id, role, content, time.time()),
        )

    async def get_recent(self, chat_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = await asyncio.to_thread(
            _db_read,
            str(self._db_path),
            "SELECT user_id, role, content, created_at FROM messages WHERE chat_id=? ORDER BY created_at DESC LIMIT ?",
            (chat_id, limit),
        )
        return [
            {"user_id": r[0], "role": r[1], "content": r[2], "timestamp": r[3]}
            for r in reversed(rows)
        ]

    async def get_last_message_id(self, chat_id: str) -> int | None:
        """Return the id of the most recent message for chat_id, or None."""
        rows = await asyncio.to_thread(
            _db_read,
            str(self._db_path),
            "SELECT id FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT 1",
            (chat_id,),
        )
        return rows[0][0] if rows else None

    async def count_since_consolidation(self, chat_id: str) -> int:
        cursor = self._consolidation_cursor.get(chat_id, 0)
        rows = await asyncio.to_thread(
            _db_read,
            str(self._db_path),
            "SELECT COUNT(*) FROM messages WHERE chat_id=? AND id>?",
            (chat_id, cursor),
        )
        return rows[0][0] if rows else 0

    async def mark_consolidated(self, chat_id: str, up_to_id: int) -> None:
        self._consolidation_cursor[chat_id] = up_to_id

    async def cleanup(self, chat_id: str, ttl_seconds: float = 7 * 86400) -> int:
        cutoff = time.time() - ttl_seconds
        cur = await asyncio.to_thread(
            _db_write,
            str(self._db_path),
            "DELETE FROM messages WHERE chat_id=? AND created_at<?",
            (chat_id, cutoff),
        )
        return cur
