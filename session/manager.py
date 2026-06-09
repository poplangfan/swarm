"""Session manager — per-chat_id conversation persistence with SQLite + FTS5.

Features:
- SQLite persistence with WAL mode for concurrent access
- FTS5 full-text search across all session messages
- LRU cache for memory-bounded operation
- Session cleanup for expired conversations
- Conversation history retrieval with token-aware trimming
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import structlog

from utils.tokens import estimate_tokens

logger = structlog.get_logger(__name__)


def _db_execute(db_path: str, sql: str, params: tuple = ()) -> list:
    """Run a SQL statement synchronously (intended for asyncio.to_thread)."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.fetchall()


class Session:
    """A single conversation session, keyed by chat_id."""

    def __init__(
        self,
        key: str,
        messages: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.key = key
        self.messages: list[dict[str, Any]] = messages or []
        self.metadata: dict[str, Any] = metadata or {}
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def add_message(self, role: str, content: str, **extra) -> None:
        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        entry.update(extra)
        self.messages.append(entry)
        self.updated_at = datetime.now(timezone.utc)

    def get_history(
        self,
        max_messages: int = 50,
        max_tokens: int | None = None,
        include_timestamps: bool = False,
    ) -> list[dict[str, Any]]:
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
            if not trimmed:
                trimmed = [result[-1]] if result else []
            return trimmed
        return result


@dataclass
class SearchResult:
    """A single FTS5 search hit."""

    session_key: str
    snippet: str  # highlighted match excerpt
    created_at: str
    updated_at: str
    message_count: int
    rank: float  # lower is better (BM25)


class SessionManager:
    """Manages conversation sessions with SQLite persistence and FTS5 search.

    Uses an LRU cache to bound memory usage in production deployments.
    FTS5 full-text search enables searching across all past conversations.
    """

    MAX_CACHED_SESSIONS = 1000

    def __init__(self, data_dir: Path, max_cached: int | None = None):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "sessions.db"
        self._cache: dict[str, Session] = {}
        self._max_cached = max_cached if max_cached is not None else self.MAX_CACHED_SESSIONS
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite schema with FTS5 support."""
        _db_execute(
            str(self._db_path),
            """CREATE TABLE IF NOT EXISTS sessions (
                key TEXT PRIMARY KEY, messages_json TEXT DEFAULT '[]',
                metadata_json TEXT DEFAULT '{}', created_at TEXT, updated_at TEXT
            )""",
        )
        _db_execute(
            str(self._db_path),
            "CREATE INDEX IF NOT EXISTS idx_sessions_upd ON sessions(updated_at)",
        )
        # FTS5 virtual table for full-text search
        _db_execute(
            str(self._db_path),
            "CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5("
            "key, messages_text, content='sessions', content_rowid='rowid'"
            ")",
        )
        # Triggers to keep FTS in sync with sessions table
        _db_execute(
            str(self._db_path),
            "CREATE TRIGGER IF NOT EXISTS sessions_ai AFTER INSERT ON sessions BEGIN "
            "INSERT INTO sessions_fts(rowid, key, messages_text) "
            "VALUES (new.rowid, new.key, new.messages_json); END;",
        )
        _db_execute(
            str(self._db_path),
            "CREATE TRIGGER IF NOT EXISTS sessions_ad AFTER DELETE ON sessions BEGIN "
            "INSERT INTO sessions_fts(sessions_fts, rowid, key, messages_text) "
            "VALUES ('delete', old.rowid, old.key, old.messages_json); END;",
        )
        _db_execute(
            str(self._db_path),
            "CREATE TRIGGER IF NOT EXISTS sessions_au AFTER UPDATE ON sessions BEGIN "
            "INSERT INTO sessions_fts(sessions_fts, rowid, key, messages_text) "
            "VALUES ('delete', old.rowid, old.key, old.messages_json); "
            "INSERT INTO sessions_fts(rowid, key, messages_text) "
            "VALUES (new.rowid, new.key, new.messages_json); END;",
        )
        logger.debug("session_db_initialized", path=str(self._db_path))

    # ── CRUD ────────────────────────────────────────────────

    async def get_or_create(self, key: str) -> Session:
        async with self._lock:
            if key in self._cache:
                return self._cache[key]
            rows = await asyncio.to_thread(
                _db_execute,
                str(self._db_path),
                "SELECT messages_json, metadata_json FROM sessions WHERE key = ?",
                (key,),
            )
            if rows:
                try:
                    s = Session(
                        key=key, messages=json.loads(rows[0][0]), metadata=json.loads(rows[0][1])
                    )
                except json.JSONDecodeError:
                    logger.warning("session_json_corrupted", key=key)
                    s = Session(key=key)
            else:
                s = Session(key=key)
            if len(self._cache) >= self._max_cached:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            self._cache[key] = s
            return s

    async def save(self, session: Session) -> None:
        async with self._lock:
            await asyncio.to_thread(
                _db_execute,
                str(self._db_path),
                "INSERT OR REPLACE INTO sessions "
                "(key, messages_json, metadata_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    session.key,
                    json.dumps(session.messages, ensure_ascii=False),
                    json.dumps(session.metadata, ensure_ascii=False),
                    session.created_at.isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    async def clear(self, key: str) -> None:
        async with self._lock:
            self._cache.pop(key, None)
            await asyncio.to_thread(
                _db_execute,
                str(self._db_path),
                "DELETE FROM sessions WHERE key = ?",
                (key,),
            )

    async def delete(self, key: str) -> None:
        await self.clear(key)

    async def cleanup_expired(self, days: int = 30) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        async with self._lock:
            _ = await asyncio.to_thread(
                _db_execute,
                str(self._db_path),
                "DELETE FROM sessions WHERE updated_at < ?",
                (cutoff,),
            )
            deleted_keys = [k for k, v in self._cache.items() if v.updated_at.isoformat() < cutoff]
            for k in deleted_keys:
                self._cache.pop(k, None)
        return len(deleted_keys) if deleted_keys else 0

    async def all_keys(self) -> list[str]:
        rows = await asyncio.to_thread(_db_execute, str(self._db_path), "SELECT key FROM sessions")
        return [r[0] for r in rows]

    # ── FTS5 Search ─────────────────────────────────────────

    async def search(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
    ) -> list[SearchResult]:
        """Full-text search across all session messages using FTS5.

        Args:
            query: FTS5 search query (supports AND, OR, NOT, "phrases", prefix*)
            limit: Max results to return.
            offset: Pagination offset.

        Returns:
            List of SearchResult objects ranked by BM25 relevance.
        """
        sql = """
        SELECT
            s.key,
            snippet(sessions_fts, 2, '<b>', '</b>', '...', 40) AS snippet,
            s.created_at,
            s.updated_at,
            json_array_length(s.messages_json) AS msg_count,
            rank
        FROM sessions_fts
        JOIN sessions s ON s.key = sessions_fts.key
        WHERE sessions_fts MATCH ?
        ORDER BY rank
        LIMIT ? OFFSET ?
        """
        rows = await asyncio.to_thread(
            _db_execute,
            str(self._db_path),
            sql,
            (query, limit, offset),
        )
        return [
            SearchResult(
                session_key=r[0],
                snippet=r[1] or "",
                created_at=r[2] or "",
                updated_at=r[3] or "",
                message_count=r[4] or 0,
                rank=r[5] or 0.0,
            )
            for r in rows
        ]

    async def search_count(self, query: str) -> int:
        """Return the number of FTS5 matches for a query."""
        rows = await asyncio.to_thread(
            _db_execute,
            str(self._db_path),
            "SELECT COUNT(*) FROM sessions_fts WHERE sessions_fts MATCH ?",
            (query,),
        )
        return rows[0][0] if rows else 0

    async def recent_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recently updated sessions with metadata."""
        rows = await asyncio.to_thread(
            _db_execute,
            str(self._db_path),
            "SELECT key, updated_at, "
            "json_array_length(messages_json) AS msg_count "
            "FROM sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        return [{"key": r[0], "updated_at": r[1], "message_count": r[2]} for r in rows]

    async def stats(self) -> dict[str, Any]:
        """Return session store statistics."""
        rows = await asyncio.to_thread(
            _db_execute,
            str(self._db_path),
            "SELECT COUNT(*), SUM(json_array_length(messages_json)) FROM sessions",
        )
        total_sessions = rows[0][0] if rows else 0
        total_messages = rows[0][1] if rows and rows[0][1] else 0
        return {
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "cached_sessions": len(self._cache),
            "cache_max": self._max_cached,
            "db_path": str(self._db_path),
        }
