"""Tests for Dream memory consolidation."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from memory.dream import DreamConsolidator
from memory.store import ChromaMemoryStore
from memory.short_term import ShortTermMemory
from providers.base import LLMResponse


class TestDreamConsolidator:
    @pytest.mark.asyncio
    async def test_no_consolidation_below_threshold(self, temp_dir):
        chroma = ChromaMemoryStore(temp_dir / "chroma")
        short_term = ShortTermMemory(temp_dir)

        for i in range(5):
            await short_term.add("chat_A", "user_1", f"msg {i}")

        dreamer = DreamConsolidator(
            chroma_store=chroma, short_term=short_term,
            consolidation_threshold=20,
        )
        result = await dreamer.maybe_consolidate("chat_A")
        assert not result["consolidated"]

    @pytest.mark.asyncio
    async def test_heuristic_extraction(self, temp_dir):
        chroma = ChromaMemoryStore(temp_dir / "chroma")
        short_term = ShortTermMemory(temp_dir)

        facts = [
            "Alice works at Acme Corp",
            "The project deadline is next Friday",
            "We need to use Python for the backend",
            "Bob likes coffee and tea",
            "The server is running Ubuntu 22.04",
            "Team meeting is every Monday at 9am",
        ]
        for f in facts:
            await short_term.add("chat_A", "user_1", f)

        dreamer = DreamConsolidator(
            chroma_store=chroma, short_term=short_term,
            consolidation_threshold=5,
        )
        result = await dreamer.maybe_consolidate("chat_A")
        assert result["consolidated"]

    @pytest.mark.asyncio
    async def test_with_llm_provider(self, temp_dir):
        """Dream consolidation with LLM extraction."""
        chroma = ChromaMemoryStore(temp_dir / "chroma")
        short_term = ShortTermMemory(temp_dir)

        for i in range(25):
            await short_term.add("chat_A", "user_1",
                          f"User said: remember that I work on Project X with task {i}")

        provider = MagicMock()
        provider.chat = AsyncMock(return_value=LLMResponse(
            content='[{"fact": "User works on Project X", "importance": 0.9, "entities": ["Project X"]}]',
            stop_reason="end_turn",
        ))

        dreamer = DreamConsolidator(
            chroma_store=chroma, short_term=short_term,
            provider=provider, consolidation_threshold=20,
        )
        result = await dreamer.maybe_consolidate("chat_A")
        assert result["consolidated"]

    @pytest.mark.asyncio
    async def test_empty_messages(self, temp_dir):
        chroma = ChromaMemoryStore(temp_dir / "chroma")
        short_term = ShortTermMemory(temp_dir)

        dreamer = DreamConsolidator(chroma_store=chroma, short_term=short_term)
        result = await dreamer.maybe_consolidate("chat_A")
        assert not result["consolidated"]

    @pytest.mark.asyncio
    async def test_consolidation_isolation(self, temp_dir):
        """Different chats have isolated consolidation."""
        chroma = ChromaMemoryStore(temp_dir / "chroma")
        short_term = ShortTermMemory(temp_dir)

        for i in range(25):
            await short_term.add("chat_A", "user_A", f"A's message {i}: Project Alpha")
        for i in range(5):
            await short_term.add("chat_B", "user_B", f"B's message {i}: Project Beta")

        dreamer = DreamConsolidator(
            chroma_store=chroma, short_term=short_term,
            consolidation_threshold=20,
        )

        result_a = await dreamer.maybe_consolidate("chat_A")
        result_b = await dreamer.maybe_consolidate("chat_B")

        assert result_a["consolidated"]
        assert not result_b["consolidated"]
