"""Session manager — per-chat_id conversation persistence with SQLite."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from utils.tokens import estimate_tokens

logger = structlog.get_logger(__name__)


def _db_execute(db_path: str, sql: str, params: tuple = ()) -> list:
    """Run a SQL statement synchronously (intended for asyncio.to_thread)."""
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.fetchall()


class Session:
    """A single conversation session, keyed by chat_id."""

    def __init__(self, key: str, messages: list[dict[str, Any]] | None = None,
                 metadata: dict[str, Any] | None = None):
        self.key = key
        self.messages: list[dict[str, Any]] = messages or []
        self.metadata: dict[str, Any] = metadata or {}
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def add_message(self, role: str, content: str, **extra) -> None:
        entry = {"role": role, "content": content,
                 "timestamp": datetime.now(timezone.utc).isoformat()}
        entry.update(extra)
        self.messages.append(entry)
        self.updated_at = datetime.now(timezone.utc)

    def get_history(self, max_messages: int = 50,
                    max_tokens: int | None = None,
                    include_timestamps: bool = False) -> list[dict[str, Any]]:
        recent = self.messages[-max_messages:]
        result = []
        for m in recent:
            entry = {"role": m["role"], "content": m["content"]}
            if include_timestamps:
                entry["timestamp"] = m.get("timestamp", "")
            result.append(entry)
        if max_tokens:
            total = 0
            trimmed = []
            for m in reversed(result):
                total += estimate_tokens(str(m.get("content", ""))) + 4
                if total > max_tokens:
                    break
                trimmed.insert(0, m)
            # Always retain at least the last message to avoid empty context
            if not trimmed:
                trimmed = [result[-1]] if result else []
            return trimmed
        return result


class SessionManager:
    """Manages conversation sessions with SQLite persistence.

    Uses an LRU cache to bound memory usage in production deployments.
    """

    MAX_CACHED_SESSIONS = 1000

    def __init__(self, data_dir: Path, max_cached: int | None = None):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "sessions.db"
        self._cache: dict[str, Session] = {}
        self._max_cached = max_cached if max_cached is not None else self.MAX_CACHED_SESSIONS
        self._lock = asyncio.Lock()
        _db_execute(str(self._db_path), """
            CREATE TABLE IF NOT EXISTS sessions (
                key TEXT PRIMARY KEY, messages_json TEXT DEFAULT '[]',
                metadata_json TEXT DEFAULT '{}', created_at TEXT, updated_at TEXT
            )
        """)
        _db_execute(str(self._db_path),
                    "CREATE INDEX IF NOT EXISTS idx_sessions_upd ON sessions(updated_at)")

    async def get_or_create(self, key: str) -> Session:
        async with self._lock:
            if key in self._cache:
                return self._cache[key]
            rows = await asyncio.to_thread(
                _db_execute, str(self._db_path),
                "SELECT messages_json, metadata_json FROM sessions WHERE key = ?", (key,),
            )
            if rows:
                try:
                    s = Session(key=key, messages=json.loads(rows[0][0]),
                                metadata=json.loads(rows[0][1]))
                except json.JSONDecodeError:
                    logger.warning("session_json_corrupted", key=key)
                    s = Session(key=key)
            else:
                s = Session(key=key)
            # LRU eviction: if cache is full, remove the oldest entry
            if len(self._cache) >= self._max_cached:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            self._cache[key] = s
            return s

    async def save(self, session: Session) -> None:
        async with self._lock:
            await asyncio.to_thread(
                _db_execute, str(self._db_path),
                "INSERT OR REPLACE INTO sessions (key, messages_json, metadata_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (session.key, json.dumps(session.messages, ensure_ascii=False),
                 json.dumps(session.metadata, ensure_ascii=False),
                 session.created_at.isoformat(), datetime.now(timezone.utc).isoformat()),
            )

    async def clear(self, key: str) -> None:
        async with self._lock:
            self._cache.pop(key, None)
            await asyncio.to_thread(
                _db_execute, str(self._db_path),
                "DELETE FROM sessions WHERE key = ?", (key,),
            )

    async def delete(self, key: str) -> None:
        await self.clear(key)

    async def cleanup_expired(self, days: int = 30) -> int:
        """Delete sessions not updated within the given number of days.

        Returns the count of deleted sessions.
        """
        cutoff = (datetime.now(timezone.utc) - __import__('datetime').timedelta(days=days)).isoformat()
        async with self._lock:
            rows = await asyncio.to_thread(
                _db_execute, str(self._db_path),
                "DELETE FROM sessions WHERE updated_at < ?", (cutoff,),
            )
            deleted = len(rows) if rows else 0
            # Also evict deleted keys from cache
            deleted_keys = [k for k, v in self._cache.items() if v.updated_at.isoformat() < cutoff]
            for k in deleted_keys:
                self._cache.pop(k, None)
        return len(deleted_keys) if deleted_keys else 0

    async def all_keys(self) -> list[str]:
        rows = await asyncio.to_thread(
            _db_execute, str(self._db_path), "SELECT key FROM sessions"
        )
        return [r[0] for r in rows]
