"""Tests for subagent system."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from agent.subagent import SubagentManager, SubagentSpec
from providers.base import LLMResponse


class TestSubagentManager:
    def test_initial_state(self, mock_provider):
        mgr = SubagentManager(provider=mock_provider)
        assert mgr.active_count == 0

    @pytest.mark.asyncio
    async def test_spawn_and_complete(self, mock_provider):
        mock_provider.chat = AsyncMock(
            return_value=LLMResponse(content="Task completed successfully", stop_reason="end_turn")
        )
        mgr = SubagentManager(provider=mock_provider, max_concurrent=3, timeout=10.0)

        spec = SubagentSpec(
            description="Count to 10",
            max_iterations=3,
            timeout=10.0,
        )
        result = await mgr.spawn(spec)
        assert result.success
        assert "completed" in result.content.lower()

    @pytest.mark.asyncio
    async def test_spawn_parallel(self, mock_provider):
        mock_provider.chat = AsyncMock(
            side_effect=[
                LLMResponse(content="Result A", stop_reason="end_turn"),
                LLMResponse(content="Result B", stop_reason="end_turn"),
                LLMResponse(content="Result C", stop_reason="end_turn"),
            ]
        )
        mgr = SubagentManager(provider=mock_provider, max_concurrent=3, timeout=10.0)

        specs = [
            SubagentSpec(description="Task 1", max_iterations=3),
            SubagentSpec(description="Task 2", max_iterations=3),
            SubagentSpec(description="Task 3", max_iterations=3),
        ]
        results = await mgr.spawn_parallel(specs)

        assert len(results) == 3
        assert all(r.success for r in results)
        contents = {r.content for r in results}
        assert "Result A" in contents
        assert "Result B" in contents
        assert "Result C" in contents

    @pytest.mark.asyncio
    async def test_timeout_handling(self, mock_provider):
        async def slow_response(*args, **kwargs):
            await asyncio.sleep(10)
            return LLMResponse(content="Too late", stop_reason="end_turn")

        mock_provider.chat = AsyncMock(side_effect=slow_response)
        mgr = SubagentManager(provider=mock_provider, max_concurrent=1, timeout=0.1)

        spec = SubagentSpec(description="Slow task", timeout=0.1)
        result = await mgr.spawn(spec)
        assert not result.success
        assert result.error is not None  # Error occurred (timeout or related)

    @pytest.mark.asyncio
    async def test_concurrency_limit(self, mock_provider):
        running = 0
        max_running = 0

        async def tracked_response(*args, **kwargs):
            nonlocal running, max_running
            running += 1
            max_running = max(max_running, running)
            await asyncio.sleep(0.05)
            running -= 1
            return LLMResponse(content="done", stop_reason="end_turn")

        mock_provider.chat = AsyncMock(side_effect=tracked_response)
        mgr = SubagentManager(provider=mock_provider, max_concurrent=2, timeout=10.0)

        specs = [SubagentSpec(description=f"Task {i}", max_iterations=2) for i in range(5)]
        results = await mgr.spawn_parallel(specs)

        assert len(results) == 5
        assert max_running <= 2  # Concurrency limit respected

    @pytest.mark.asyncio
    async def test_cancel_by_session(self, mock_provider):
        async def slow(*args, **kwargs):
            await asyncio.sleep(60)
            return LLMResponse(content="never", stop_reason="end_turn")

        mock_provider.chat = AsyncMock(side_effect=slow)
        mgr = SubagentManager(provider=mock_provider)

        # Start a subagent but don't wait for it
        spec = SubagentSpec(
            task_id="session_A_task_1",
            description="Long task",
            timeout=60.0,
        )
        # Start in background
        task = asyncio.create_task(mgr.spawn(spec))
        await asyncio.sleep(0.05)  # Let it start

        cancelled = await mgr.cancel_by_session("session_A")
        # Should have cancelled at least the one we started
        await asyncio.sleep(0.05)
        assert cancelled >= 1 or task.done()


class TestSubagentSpec:
    def test_defaults(self):
        spec = SubagentSpec(description="Test task")
        assert spec.description == "Test task"
        assert spec.max_iterations == 15
        assert spec.timeout == 300.0
        assert len(spec.task_id) > 0

    def test_custom_values(self):
        spec = SubagentSpec(
            task_id="custom_id",
            description="Custom",
            max_iterations=5,
            timeout=60.0,
            parent_trace_id="parent_123",
        )
        assert spec.task_id == "custom_id"
        assert spec.max_iterations == 5
        assert spec.timeout == 60.0
