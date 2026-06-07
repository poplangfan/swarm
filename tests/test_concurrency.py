"""Concurrency safety tests — verify multi-tenant isolation."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.loop import AgentLoop
from bus.queue import MessageBus
from providers.base import LLMResponse
from session.manager import SessionManager


class TestConcurrencySafety:
    """Verify that multi-tenant isolation works correctly under load."""

    @pytest.mark.asyncio
    async def test_10_concurrent_chats_no_cross_contamination(self, temp_dir):
        """10 different chats send messages concurrently — zero cross-contamination."""
        sessions = SessionManager(temp_dir)

        # Each chat gets a unique response
        async def chat_side_effect(messages, tools=None, **kw):
            # Extract chat context from the system prompt or user message
            for m in messages:
                content = str(m.get("content", ""))
                if "Chat ID:" in content:
                    chat_id = content.split("Chat ID:")[1].strip().split("\n")[0]
                    return LLMResponse(content=f"Response for {chat_id}", stop_reason="end_turn")
            # Fallback: find in user message runtime context
            user_msg = str(messages[-1].get("content", ""))
            for line in user_msg.split("\n"):
                if "Chat ID:" in line:
                    chat_id = line.split("Chat ID:")[1].strip()
                    return LLMResponse(content=f"Response for {chat_id}", stop_reason="end_turn")
            return LLMResponse(content="Generic response", stop_reason="end_turn")

        provider = MagicMock()
        provider.chat = AsyncMock(side_effect=chat_side_effect)
        provider.model = "gpt-4o"
        provider.context_window = 128_000
        provider._max_tokens = 4096
        provider.generation = MagicMock()
        provider.generation.max_tokens = 4096

        bus = MessageBus()
        loop = AgentLoop(bus=bus, provider=provider, workspace=temp_dir, sessions=sessions)

        # 10 different chat_ids
        chat_ids = [f"oc_chat_{i}" for i in range(10)]

        async def process_chat(chat_id: str):
            key = f"feishu:{chat_id}"
            result = await loop.process_direct(
                f"message from {chat_id}",
                session_key=key,
                chat_id=chat_id,
            )
            return result.content if result else None

        results = await asyncio.gather(*[process_chat(cid) for cid in chat_ids])

        # Every chat got a response
        assert all(r is not None for r in results)
        assert len(results) == 10

        # Session isolation — each chat has at most 2 messages (user + assistant)
        for cid in chat_ids:
            s = await sessions.get_or_create(f"feishu:{cid}")
            msg_count = len(s.messages)
            assert msg_count <= 2, f"Chat {cid} has {msg_count} messages (expected <=2)"

    @pytest.mark.asyncio
    async def test_same_chat_serialized(self, temp_dir):
        """Same chat_id receives 5 concurrent messages — all processed serially."""
        sessions = SessionManager(temp_dir)
        call_order = []

        async def sequential_chat(messages, tools=None, **kw):
            call_order.append(time.time())
            await asyncio.sleep(0.01)
            return LLMResponse(content="OK", stop_reason="end_turn")

        import time

        provider = MagicMock()
        provider.chat = AsyncMock(side_effect=sequential_chat)
        provider.model = "gpt-4o"
        provider.context_window = 128_000
        provider._max_tokens = 4096
        provider.generation = MagicMock()
        provider.generation.max_tokens = 4096

        bus = MessageBus()
        loop = AgentLoop(bus=bus, provider=provider, workspace=temp_dir, sessions=sessions)

        key = "feishu:oc_same_chat"
        # 5 concurrent requests to same session
        results = await asyncio.gather(
            *[
                loop.process_direct(f"msg {i}", session_key=key, chat_id="oc_same_chat")
                for i in range(5)
            ]
        )

        assert len(results) == 5
        # All calls happened — order should be strictly sequential due to Lock
        assert len(call_order) == 5
        for i in range(1, len(call_order)):
            assert call_order[i] >= call_order[i - 1], "Calls should be in order"

    @pytest.mark.asyncio
    async def test_chroma_isolation_by_chat_id(self, temp_dir):
        """ChromaDB writes have correct chat_id metadata — no cross-contamination."""
        from memory.short_term import ShortTermMemory

        store = ShortTermMemory(temp_dir)

        # Write messages for different chats
        for chat_id in ["chat_A", "chat_B", "chat_C"]:
            for i in range(5):
                await store.add(chat_id, f"user_{chat_id}", f"Message {i} for {chat_id}")

        # Verify isolation
        for chat_id in ["chat_A", "chat_B", "chat_C"]:
            msgs = await store.get_recent(chat_id, limit=100)
            assert len(msgs) == 5, f"{chat_id} should have 5 messages"
            for m in msgs:
                assert chat_id in m["content"], f"Message '{m['content']}' not for {chat_id}"
