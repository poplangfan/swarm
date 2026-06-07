"""Persistent state store — survive restarts with SQLite + JSON."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _db_execute(db_path: str, sql: str, params: tuple = ()) -> list:
    """Run a SQL statement synchronously (intended for asyncio.to_thread)."""
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.fetchall()


def _db_query(db_path: str, sql: str, params: tuple = ()) -> list:
    """Run a read-only SQL query synchronously (intended for asyncio.to_thread)."""
    with sqlite3.connect(db_path) as conn:
        return conn.execute(sql, params).fetchall()


class StateStore:
    """Key-value state store with SQLite persistence.

    Used for framework-level state that must survive restarts:
    - App ticket cache (for Feishu event verification)
    - Cursor positions (for polling-based operations)
    - Configuration hashes (for change detection)
    """

    def __init__(self, data_dir: Path):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = str(self._data_dir / "state.db")
        self._cache: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        _db_execute(
            self._db_path,
            """
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """,
        )

    async def get(self, key: str, default: Any = None) -> Any:
        """Get a state value by key."""
        if key in self._cache:
            return self._cache[key]

        rows = await asyncio.to_thread(
            _db_query,
            self._db_path,
            "SELECT value_json FROM state WHERE key=?",
            (key,),
        )
        if rows:
            value = json.loads(rows[0][0])
            self._cache[key] = value
            return value
        return default

    async def set(self, key: str, value: Any) -> None:
        """Set a state value."""
        async with self._lock:
            self._cache[key] = value
            await asyncio.to_thread(
                _db_execute,
                self._db_path,
                "INSERT OR REPLACE INTO state (key, value_json, updated_at) VALUES (?,?,?)",
                (key, json.dumps(value), time.time()),
            )

    async def delete(self, key: str) -> None:
        """Delete a state key."""
        self._cache.pop(key, None)
        await asyncio.to_thread(
            _db_execute,
            self._db_path,
            "DELETE FROM state WHERE key=?",
            (key,),
        )

    async def exists(self, key: str) -> bool:
        """Check if a key exists (lightweight — no JSON deserialization)."""
        if key in self._cache:
            return True
        rows = await asyncio.to_thread(
            _db_query,
            self._db_path,
            "SELECT 1 FROM state WHERE key=? LIMIT 1",
            (key,),
        )
        return len(rows) > 0

    async def keys(self) -> list[str]:
        """List all state keys."""
        rows = await asyncio.to_thread(_db_query, self._db_path, "SELECT key FROM state")
        return [r[0] for r in rows]

    async def get_all(self) -> dict[str, Any]:
        """Get all state as a dict."""
        rows = await asyncio.to_thread(
            _db_query, self._db_path, "SELECT key, value_json FROM state"
        )
        return {r[0]: json.loads(r[1]) for r in rows}
