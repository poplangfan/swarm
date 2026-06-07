"""Hybrid memory recall — vector similarity + time decay + importance weighting."""

from __future__ import annotations

import math
import time
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class MemoryRecall:
    """Hybrid recall: ChromaDB vector search with time decay and importance weighting."""

    def __init__(self, chroma_store=None, short_term=None, use_chromadb: bool = True):
        self._chroma = chroma_store
        self._short_term = short_term
        self._use_chromadb = use_chromadb

    async def query(
        self, query_text: str, chat_id: str, k: int = 10, time_decay_days: float = 30.0
    ) -> list[dict[str, Any]]:
        results = []
        if self._chroma and self._use_chromadb:
            try:
                results = await self._chroma.query(chat_id, query_text, k=k)
            except Exception as e:
                logger.warning("chroma_recall_failed", chat_id=chat_id, error=str(e))
        now = time.time()
        for r in results:
            ts_str = (r.get("metadata") or {}).get("timestamp", "")
            importance = float((r.get("metadata") or {}).get("importance", 0.5))
            try:
                msg_time = datetime.fromisoformat(ts_str).timestamp() if ts_str else now
            except (ValueError, TypeError):
                msg_time = now
            age_days = max(0, (now - msg_time) / 86400)
            r["_score"] = importance * math.exp(-age_days / max(1, time_decay_days))
        results.sort(key=lambda r: r.get("_score", 0), reverse=True)
        return results[:k]
