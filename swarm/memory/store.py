"""ChromaDB vector memory store — collections per chat_id for isolation."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False


class ChromaMemoryStore:
    """Vector memory using ChromaDB. Each chat_id gets its own collection."""

    def __init__(self, persist_dir: str | Path, embedding_model: str = "all-MiniLM-L6-v2"):
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = None
        self._ef = None
        if HAS_CHROMADB:
            try:
                self._client = chromadb.PersistentClient(
                    path=str(self._persist_dir),
                    settings=Settings(anonymized_telemetry=False),
                )
            except Exception:
                logger.warning("chromadb_init_failed", exc_info=True)

    def _collection_name(self, chat_id: str) -> str:
        safe = chat_id.replace(":", "_").replace("/", "_")
        return f"mem_{safe}"

    async def add(self, chat_id: str, user_id: str, content: str,
                  importance: float = 0.5, metadata: dict | None = None) -> bool:
        if self._client is None:
            return False
        try:
            col = await asyncio.to_thread(
                self._client.get_or_create_collection, name=self._collection_name(chat_id))
            meta = {"user_id": user_id, "importance": importance,
                    "timestamp": datetime.now().isoformat()}
            if metadata:
                meta.update(metadata)
            await asyncio.to_thread(
                col.add, documents=[content], metadatas=[meta],
                ids=[f"{chat_id}_{uuid.uuid4()}"])
            return True
        except Exception:
            logger.exception("memory_add_failed")
            return False

    async def query(self, chat_id: str, query_text: str, k: int = 10) -> list[dict[str, Any]]:
        if self._client is None:
            return []
        try:
            col_name = self._collection_name(chat_id)
            try:
                col = await asyncio.to_thread(
                    self._client.get_collection, name=col_name)
            except Exception:
                return []
            results = await asyncio.to_thread(
                col.query, query_texts=[query_text], n_results=k)
            if not results or not results.get("documents") or not results["documents"][0]:
                return []
            entries = []
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                entries.append({"content": doc, "metadata": meta})
            return entries
        except Exception:
            return []

    def delete_collection(self, chat_id: str) -> None:
        if self._client is None:
            return
        try:
            self._client.delete_collection(name=self._collection_name(chat_id))
        except Exception:
            pass
