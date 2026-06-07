"""Tests for session manager — per-chat_id isolation."""

import pytest
from session.manager import Session, SessionManager


class TestSession:
    def test_add_and_get_messages(self):
        s = Session(key="test:chat_A")
        s.add_message("user", "hello")
        s.add_message("assistant", "hi there")
        assert len(s.messages) == 2
        assert s.messages[0]["role"] == "user"
        assert s.messages[1]["role"] == "assistant"

    def test_get_history_respects_limit(self):
        s = Session(key="test:chat_A")
        for i in range(100):
            s.add_message("user", f"msg {i}")
        history = s.get_history(max_messages=10)
        assert len(history) == 10

    def test_get_history_token_budget(self):
        s = Session(key="test:chat_A")
        s.add_message("user", "short msg")
        history = s.get_history(max_tokens=1000)
        assert len(history) >= 1

    def test_get_history_empty_retains_last(self):
        s = Session(key="test:chat_A")
        s.add_message("user", "a" * 10000)  # Very long message, exceeds budget
        history = s.get_history(max_tokens=10)
        # Should retain at least the last message even if over budget
        assert len(history) == 1


class TestSessionManager:
    @pytest.mark.asyncio
    async def test_create_and_retrieve(self, temp_dir):
        mgr = SessionManager(temp_dir)
        s = await mgr.get_or_create("test:chat_A")
        assert s.key == "test:chat_A"
        assert (await mgr.get_or_create("test:chat_A")) is s

    @pytest.mark.asyncio
    async def test_save_and_reload(self, temp_dir):
        mgr = SessionManager(temp_dir)
        s = await mgr.get_or_create("test:chat_B")
        s.add_message("user", "persist me")
        await mgr.save(s)
        mgr2 = SessionManager(temp_dir)
        s2 = await mgr2.get_or_create("test:chat_B")
        assert len(s2.messages) == 1
        assert s2.messages[0]["content"] == "persist me"

    @pytest.mark.asyncio
    async def test_isolation(self, temp_dir):
        mgr = SessionManager(temp_dir)
        s_a = await mgr.get_or_create("test:chat_A")
        s_b = await mgr.get_or_create("test:chat_B")
        s_a.add_message("user", "A's msg")
        s_b.add_message("user", "B's msg")
        await mgr.save(s_a)
        await mgr.save(s_b)
        mgr2 = SessionManager(temp_dir)
        assert (await mgr2.get_or_create("test:chat_A")).messages[0]["content"] == "A's msg"
        assert (await mgr2.get_or_create("test:chat_B")).messages[0]["content"] == "B's msg"

    @pytest.mark.asyncio
    async def test_clear(self, temp_dir):
        mgr = SessionManager(temp_dir)
        s = await mgr.get_or_create("test:chat_C")
        s.add_message("user", "hello")
        await mgr.save(s)
        await mgr.clear("test:chat_C")
        assert len((await mgr.get_or_create("test:chat_C")).messages) == 0
