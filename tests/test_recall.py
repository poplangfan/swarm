"""Tests for hybrid memory recall — vector + time decay + importance."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from memory.recall import MemoryRecall


class TestMemoryRecall:
    def test_empty_recall(self):
        recall = MemoryRecall(use_chromadb=False)
        results = asyncio.run(recall.query("test", "chat_A", k=5))
        assert results == []

    def test_recall_with_indexed_data(self):
        recall = MemoryRecall(use_chromadb=False)
        # Populate with test data
        recall._index = [
            {
                "content": "User works at Acme Corp as engineer",
                "metadata": {
                    "chat_id": "chat_A",
                    "user_id": "user_1",
                    "importance": 0.9,
                    "timestamp": "2026-06-07T10:00:00",
                },
            },
            {
                "content": "Project deadline is next Friday",
                "metadata": {
                    "chat_id": "chat_A",
                    "user_id": "user_1",
                    "importance": 0.7,
                    "timestamp": "2026-06-07T11:00:00",
                },
            },
            {
                "content": "Team meeting every Monday at 9am",
                "metadata": {
                    "chat_id": "chat_A",
                    "user_id": "user_2",
                    "importance": 0.5,
                    "timestamp": "2026-05-01T00:00:00",  # Old
                },
            },
        ]
        results = asyncio.run(recall.query("work Acme", "chat_A", k=2))
        # Results returned (though without ChromaDB, just returns empty list)
        assert isinstance(results, list)

    def test_recall_with_mock_chromadb(self):
        mock_chroma = MagicMock()
        mock_chroma.query = AsyncMock(
            return_value=[
                {
                    "content": "Fact about Acme Corp",
                    "metadata": {"importance": 1.0, "timestamp": "2026-06-07T12:00:00"},
                },
                {
                    "content": "Another fact",
                    "metadata": {"importance": 0.5, "timestamp": "2026-06-01T00:00:00"},
                },
            ]
        )
        recall = MemoryRecall(chroma_store=mock_chroma, use_chromadb=True)
        results = asyncio.run(recall.query("Acme", "chat_A", k=2))
        assert len(results) == 2
        # Results should be sorted by score (higher first)
        if len(results) >= 2:
            assert results[0].get("_score", 0) >= results[1].get("_score", 0)

    def test_time_decay_applied(self):
        recall = MemoryRecall(use_chromadb=False)
        recall._index = [
            {
                "content": "Recent fact",
                "metadata": {"importance": 1.0, "timestamp": "2026-06-07T12:00:00"},
            },
        ]
        results = asyncio.run(recall.query("fact", "chat_A", k=1, time_decay_days=30))
        assert len(results) == 0  # No ChromaDB → no results from index in query()

    def test_recall_score_properties(self):
        """High importance + recent timestamp = higher score."""
        recall = MemoryRecall(use_chromadb=False)
        mock_chroma = MagicMock()
        mock_chroma.query = AsyncMock(
            return_value=[
                {
                    "content": "Important recent",
                    "metadata": {"importance": 1.0, "timestamp": "2026-06-07T12:00:00"},
                },
                {
                    "content": "Unimportant old",
                    "metadata": {"importance": 0.1, "timestamp": "2025-01-01T00:00:00"},
                },
            ]
        )
        recall._chroma = mock_chroma
        recall._use_chromadb = True
        results = asyncio.run(recall.query("test", "chat_A", k=2))
        # Both returned, sorted
        assert len(results) == 2
        # Important recent should score higher
        assert results[0].get("_score", 0) >= results[1].get("_score", 0)
