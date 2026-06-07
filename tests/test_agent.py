"""Tests for agent core: context, runner, loop."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from agent.context import RequestContext
from agent.runner import AgentRunner, AgentRunSpec, AgentRunResult
from agent.loop import AgentLoop, TurnState
from bus.queue import MessageBus
from providers.base import LLMResponse


class TestRequestContext:
    def test_immutable(self):
        ctx = RequestContext(trace_id="t1", chat_id="chat_A", chat_type="p2p",
                            user_id="user_1", message_id="msg_1")
        with pytest.raises(Exception):
            ctx.chat_id = "chat_B"

    def test_defaults(self):
        ctx = RequestContext(trace_id="t1", chat_id="c1", chat_type="p2p",
                            user_id="u1", message_id="m1")
        assert ctx.user_token is None
        assert ctx.permissions == frozenset()

    def test_with_token(self):
        ctx = RequestContext(trace_id="t1", chat_id="c1", chat_type="p2p",
                            user_id="u1", message_id="m1", user_token="tok_xxx")
        assert ctx.user_token == "tok_xxx"


class TestStateMachine:
    def test_transitions_defined(self):
        transitions = AgentLoop._TRANSITIONS
        assert (TurnState.RESTORE, "ok") in transitions
        assert (TurnState.BUILD, "ok") in transitions
        assert (TurnState.BUILD, "cmd") in transitions
        assert (TurnState.RUN, "ok") in transitions
        assert (TurnState.SAVE, "ok") in transitions
        assert (TurnState.RESPOND, "ok") in transitions

    def test_all_sources_have_transitions(self):
        transitions = AgentLoop._TRANSITIONS
        sources = {t[0] for t in transitions}
        for state in (TurnState.RESTORE, TurnState.BUILD, TurnState.RUN,
                      TurnState.SAVE, TurnState.RESPOND):
            assert state in sources, f"{state} has no outgoing transitions"


class TestAgentRunner:
    @pytest.mark.asyncio
    async def test_simple_response(self):
        provider = MagicMock()
        provider.chat = AsyncMock(return_value=LLMResponse(
            content="Hello!", stop_reason="end_turn"))
        runner = AgentRunner(provider)
        spec = AgentRunSpec(initial_messages=[{"role": "user", "content": "hi"}])
        result = await runner.run(spec)
        assert result.final_content == "Hello!"
        assert result.stop_reason == "end_turn"

    @pytest.mark.asyncio
    async def test_handles_timeout(self):
        provider = MagicMock()
        async def slow(*args, **kwargs):
            await asyncio.sleep(10)
        provider.chat = AsyncMock(side_effect=slow)
        runner = AgentRunner(provider)
        spec = AgentRunSpec(
            initial_messages=[{"role": "user", "content": "hi"}],
            llm_timeout_s=0.01,
        )
        result = await runner.run(spec)
        assert result.stop_reason == "error"


class TestAgentLoop:
    @pytest.mark.asyncio
    async def test_direct_process(self, mock_provider):
        bus = MessageBus()
        mock_provider.chat = AsyncMock(return_value=LLMResponse(
            content="Hi there!", stop_reason="end_turn"))
        loop = AgentLoop(bus=bus, provider=mock_provider, workspace=".")
        result = await loop.process_direct("hello", session_key="test:direct")
        assert result is not None
        assert "Hi there" in result.content

    @pytest.mark.asyncio
    async def test_command_skips_llm(self, mock_provider):
        bus = MessageBus()
        loop = AgentLoop(bus=bus, provider=mock_provider, workspace=".")
        result = await loop.process_direct("/help", session_key="test:direct")
        assert result is not None
        assert mock_provider.chat.call_count == 0

    @pytest.mark.asyncio
    async def test_concurrent_different_sessions(self, mock_provider):
        bus = MessageBus()
        responses = ["Response A", "Response B"]
        mock_provider.chat = AsyncMock(side_effect=[
            LLMResponse(content=r, stop_reason="end_turn") for r in responses
        ])
        loop = AgentLoop(bus=bus, provider=mock_provider, workspace=".")
        r1, r2 = await asyncio.gather(
            loop.process_direct("A", session_key="test:A"),
            loop.process_direct("B", session_key="test:B"),
        )
        assert r1.content in responses
        assert r2.content in responses
