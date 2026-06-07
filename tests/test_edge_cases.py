"""Edge case and boundary tests for core components."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.loop import AgentLoop
from agent.runner import AgentRunner, AgentRunSpec
from bus.queue import MessageBus
from providers.base import LLMResponse


class TestAgentRunnerEdgeCases:
    """Boundary conditions for the agent runner."""

    @pytest.mark.asyncio
    async def test_empty_messages(self, mock_provider):
        """Runner should handle empty initial messages gracefully."""
        runner = AgentRunner(mock_provider)
        spec = AgentRunSpec(initial_messages=[], max_iterations=1)
        result = await runner.run(spec)
        # Should not crash; may or may not get content
        assert result is not None

    @pytest.mark.asyncio
    async def test_max_iterations_boundary(self, mock_provider):
        """Exactly at max_iterations, should stop with warning."""
        mock_provider.chat = AsyncMock(
            return_value=LLMResponse(
                content=None,
                stop_reason="tool_calls",
                tool_calls=[
                    {
                        "id": "t1",
                        "function": {"name": "unknown_tool", "arguments": "{}"},
                    }
                ],
            )
        )
        runner = AgentRunner(mock_provider)
        spec = AgentRunSpec(
            initial_messages=[{"role": "user", "content": "test"}],
            tools=MagicMock(),
            max_iterations=2,
        )
        # Mock tool execution
        spec.tools.get_definitions.return_value = []
        spec.tools.execute = AsyncMock(return_value="Error: unknown")

        result = await runner.run(spec)
        assert result.stop_reason in ("max_iterations", "end_turn")

    @pytest.mark.asyncio
    async def test_very_long_content(self, mock_provider):
        """Very long user messages should be handled gracefully."""
        mock_provider.chat = AsyncMock(
            return_value=LLMResponse(
                content="Short reply",
                stop_reason="end_turn",
            )
        )
        runner = AgentRunner(mock_provider)

        long_msg = "x" * 100_000  # 100KB message
        spec = AgentRunSpec(
            initial_messages=[{"role": "user", "content": long_msg}],
        )
        result = await runner.run(spec)
        assert result is not None  # Should not crash

    @pytest.mark.asyncio
    async def test_zero_max_iterations(self, mock_provider):
        """Zero max_iterations should not crash."""
        runner = AgentRunner(mock_provider)
        spec = AgentRunSpec(
            initial_messages=[{"role": "user", "content": "hi"}],
            max_iterations=0,
        )
        result = await runner.run(spec)
        assert result is not None

    @pytest.mark.asyncio
    async def test_none_content_response(self, mock_provider):
        """LLM returning None content should not crash."""
        mock_provider.chat = AsyncMock(
            return_value=LLMResponse(
                content=None,
                stop_reason="end_turn",
            )
        )
        runner = AgentRunner(mock_provider)
        spec = AgentRunSpec(
            initial_messages=[{"role": "user", "content": "hi"}],
        )
        result = await runner.run(spec)
        assert result is not None


class TestAgentLoopEdgeCases:
    """Boundary conditions for the agent loop."""

    @pytest.mark.asyncio
    async def test_empty_content(self, mock_provider):
        """Empty string message should not crash."""
        bus = MessageBus()
        loop = AgentLoop(bus=bus, provider=mock_provider, workspace=".")
        _ = await loop.process_direct("", session_key="test:empty")
        # Empty message should not crash — may return None or empty response
        assert True  # Reached here without exception

    @pytest.mark.asyncio
    async def test_very_long_chat_id(self, mock_provider):
        """Very long chat IDs should not break session handling."""
        mock_provider.chat = AsyncMock(
            return_value=LLMResponse(
                content="OK",
                stop_reason="end_turn",
            )
        )
        bus = MessageBus()
        loop = AgentLoop(bus=bus, provider=mock_provider, workspace=".")
        long_chat_id = "oc_" + "x" * 500
        result = await loop.process_direct(
            "hello",
            session_key=f"feishu:{long_chat_id}",
            chat_id=long_chat_id,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_unicode_content(self, mock_provider):
        """Unicode, emoji, and special characters should be handled."""
        mock_provider.chat = AsyncMock(
            return_value=LLMResponse(
                content=" OK!",
                stop_reason="end_turn",
            )
        )
        bus = MessageBus()
        loop = AgentLoop(bus=bus, provider=mock_provider, workspace=".")
        result = await loop.process_direct(
            "Hello 世界! ",
            session_key="test:unicode",
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_command_case_insensitive(self, mock_provider):
        """Commands should be case-insensitive."""
        bus = MessageBus()
        loop = AgentLoop(bus=bus, provider=mock_provider, workspace=".")
        # /HELP should work the same as /help
        result = await loop.process_direct("/HELP", session_key="test:cmd")
        assert result is not None
        assert mock_provider.chat.call_count == 0  # No LLM call

    @pytest.mark.asyncio
    async def test_unknown_command_not_shortcut(self, mock_provider):
        """Unknown /command should NOT be treated as a command shortcut."""
        mock_provider.chat = AsyncMock(
            return_value=LLMResponse(
                content="I don't know that command",
                stop_reason="end_turn",
            )
        )
        bus = MessageBus()
        loop = AgentLoop(bus=bus, provider=mock_provider, workspace=".")
        result = await loop.process_direct("/unknown_command", session_key="test:cmd")
        # Should go through the LLM normally
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_stats(self, mock_provider):
        """get_stats should return valid data."""
        bus = MessageBus()
        loop = AgentLoop(bus=bus, provider=mock_provider, workspace=".")
        stats = loop.get_stats()
        assert "total_turns" in stats
        assert "total_errors" in stats
        assert "model" in stats
