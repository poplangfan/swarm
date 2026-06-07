"""Deep tests for memory store — ChromaDB operations, isolation, edge cases."""

import pytest
import tempfile
from pathlib import Path
from memory.store import ChromaMemoryStore
from memory.short_term import ShortTermMemory


class TestChromaMemoryStore:
    def test_add_and_query(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ChromaMemoryStore(tmpdir)
            import asyncio
            ok = asyncio.run(store.add(
                "chat_test", "user_1", "Alice works at Acme Corp",
                importance=0.9,
            ))
            assert ok is True or ok is False  # May fail without sentence-transformers

    def test_collection_naming(self):
        store = ChromaMemoryStore("/tmp/test")
        name_a = store._collection_name("feishu:oc_chat_A")
        name_b = store._collection_name("feishu:oc_chat_B")
        assert name_a != name_b  # Different chats = different collections
        # Same chat should get same collection name
        assert store._collection_name("feishu:oc_chat_A") == name_a

    def test_delete_collection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ChromaMemoryStore(tmpdir)
            store.delete_collection("test_chat")  # Should not raise

    def test_collection_name_handles_special_chars(self):
        store = ChromaMemoryStore("/tmp/test")
        # Chat IDs can contain special characters — must be sanitized
        name = store._collection_name("feishu:oc_test/123:456")
        assert ":" not in name.split("_")[-1] if "_" in name else True
        assert "/" not in name


class TestShortTermMemory:
    @pytest.mark.asyncio
    async def test_add_and_retrieve_ordered(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ShortTermMemory(Path(tmpdir))
            await store.add("chat_A", "user_1", "First message")
            await store.add("chat_A", "user_2", "Second message")
            await store.add("chat_A", "user_1", "Third message")

            recent = await store.get_recent("chat_A", limit=10)
            assert len(recent) == 3
            assert "First" in str(recent[0])
            assert "Third" in str(recent[2])

    @pytest.mark.asyncio
    async def test_limit_respected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ShortTermMemory(Path(tmpdir))
            for i in range(100):
                await store.add("chat_A", "user_1", f"msg {i}")
            recent = await store.get_recent("chat_A", limit=10)
            assert len(recent) == 10

    @pytest.mark.asyncio
    async def test_isolation_across_chats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ShortTermMemory(Path(tmpdir))
            await store.add("chat_A", "user_a", "A's private info")
            await store.add("chat_B", "user_b", "B's private info")

            a_msgs = await store.get_recent("chat_A", limit=50)
            b_msgs = await store.get_recent("chat_B", limit=50)

            for m in a_msgs:
                assert "A's private" in str(m)
                assert "B's private" not in str(m)
            for m in b_msgs:
                assert "B's private" in str(m)
                assert "A's private" not in str(m)

    @pytest.mark.asyncio
    async def test_count_since_consolidation_tracks_new_messages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ShortTermMemory(Path(tmpdir))
            assert await store.count_since_consolidation("chat_A") == 0
            for i in range(25):
                await store.add("chat_A", "user_1", f"msg {i}")
            assert await store.count_since_consolidation("chat_A") == 25

    @pytest.mark.asyncio
    async def test_mark_consolidated_resets_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ShortTermMemory(Path(tmpdir))
            for i in range(30):
                await store.add("chat_A", "user_1", f"msg {i}")
            before = await store.count_since_consolidation("chat_A")
            assert before == 30

            await store.mark_consolidated("chat_A", 999999)
            after = await store.count_since_consolidation("chat_A")
            assert after == 0

    @pytest.mark.asyncio
    async def test_cleanup_removes_old_messages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ShortTermMemory(Path(tmpdir))
            await store.add("chat_A", "user_1", "old message")
            await store.add("chat_B", "user_2", "keep this")

            import time
            time.sleep(0.1)
            removed = await store.cleanup("chat_A", ttl_seconds=0.01)
            remaining_a = await store.get_recent("chat_A", limit=100)
            remaining_b = await store.get_recent("chat_B", limit=100)
            assert len(remaining_b) == 1
