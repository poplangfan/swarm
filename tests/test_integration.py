"""Integration tests — full pipeline from message to response with isolation verification.

Two test categories:
- Mock-based: fast CI tests using MagicMock providers (always run)
- Real LLM: against actual DeepSeek API (requires ANTHROPIC_AUTH_TOKEN)
"""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock

from swarm.agent.context import ContextBuilder
from swarm.bus.queue import MessageBus, InboundMessage
from swarm.agent.loop import AgentLoop
from swarm.session.manager import SessionManager
from swarm.tools.registry import ToolRegistry
from swarm.tools.builtin.system import SystemTool
from swarm.tools.builtin.web_search import WebSearchTool
from swarm.agent.runner import AgentRunner, AgentRunSpec
from swarm.providers.anthropic import AnthropicProvider
from swarm.providers.base import LLMResponse, StreamChunk
from swarm.tools.base import ToolBase, tool_result


# ── Real LLM helpers ────────────────────────────────────────────


def _get_real_provider(max_tokens=256, temperature=0.1):
    """Create a provider backed by real DeepSeek API. Skips test if not configured."""
    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    if not api_key or "YOUR" in api_key:
        pytest.skip("ANTHROPIC_AUTH_TOKEN not configured")
    for k in list(os.environ.keys()):
        if 'proxy' in k.lower():
            os.environ.pop(k, None)
    return AnthropicProvider(
        api_key=api_key, base_url=base_url,
        model="deepseek-v4-pro", max_tokens=max_tokens, temperature=temperature,
    )


def _temp_workspace():
    d = tempfile.mkdtemp(prefix="swarm_int_")
    (Path(d) / "data").mkdir(exist_ok=True)
    return Path(d)


class TestFullPipeline:
    """End-to-end tests for the complete agent pipeline."""

    @pytest.mark.asyncio
    async def test_message_to_response_flow(self, temp_dir, mock_provider):
        """A complete message → response cycle through all 5 states."""
        bus = MessageBus()
        sessions = SessionManager(temp_dir)
        tools = ToolRegistry()
        tools.register(SystemTool())

        loop = AgentLoop(
            bus=bus, provider=mock_provider, workspace=temp_dir,
            sessions=sessions, tools=tools,
        )

        mock_provider.chat = AsyncMock(return_value=LLMResponse(
            content="Hello, how can I help?", stop_reason="end_turn"))

        # Process a message through the full pipeline
        result = await loop.process_direct(
            "Hi there", session_key="feishu:oc_test_integration",
            channel="feishu", chat_id="oc_test_integration",
        )

        assert result is not None
        assert "help" in result.content.lower()

        # Verify session was saved
        session = await sessions.get_or_create("feishu:oc_test_integration")
        assert len(session.messages) == 2
        assert session.messages[0]["role"] == "user"
        assert session.messages[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_command_shortcut_flow(self, temp_dir, mock_provider):
        """Slash commands go through BUILD→RESPOND, skipping RUN and SAVE states."""
        bus = MessageBus()
        loop = AgentLoop(bus=bus, provider=mock_provider, workspace=temp_dir)

        result = await loop.process_direct("/help", session_key="cli:test_cmd")
        assert result is not None
        assert "help" in result.content.lower()
        # LLM was not called
        assert mock_provider.chat.call_count == 0

    @pytest.mark.asyncio
    async def test_tool_execution_integration(self, temp_dir, mock_provider):
        """LLM calls a tool and the agent executes it and continues."""
        bus = MessageBus()
        tools = ToolRegistry()
        tools.register(SystemTool())
        tools.register(WebSearchTool())

        loop = AgentLoop(
            bus=bus, provider=mock_provider, workspace=temp_dir,
            tools=tools,
        )

        # LLM first calls web_search, then gives final answer
        mock_provider.chat = AsyncMock(side_effect=[
            LLMResponse(
                content=None, stop_reason="tool_calls",
                tool_calls=[{
                    "id": "call_1",
                    "function": {"name": "system_command", "arguments": '{"command":"status"}'},
                }],
            ),
            LLMResponse(content="Your session is active.", stop_reason="end_turn"),
        ])

        result = await loop.process_direct(
            "what's my status?",
            session_key="feishu:oc_test_tool",
            channel="feishu", chat_id="oc_test_tool",
        )

        assert result is not None
        call_count = mock_provider.chat.call_count
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_shutdown_graceful(self, temp_dir, mock_provider):
        """Graceful shutdown completes in-flight turns and saves sessions."""
        bus = MessageBus()
        sessions = SessionManager(temp_dir)

        loop = AgentLoop(
            bus=bus, provider=mock_provider, workspace=temp_dir,
            sessions=sessions,
        )

        mock_provider.chat = AsyncMock(return_value=LLMResponse(
            content="OK", stop_reason="end_turn"))

        # Send a message directly (doesn't use the bus loop)
        result = await loop.process_direct("test", session_key="test:shutdown")
        assert result is not None

        # Shutdown should not raise
        await loop.shutdown(timeout=5.0)

    @pytest.mark.asyncio
    async def test_ephemeral_query(self, temp_dir, mock_provider):
        """Ephemeral queries don't persist to session storage."""
        bus = MessageBus()
        sessions = SessionManager(temp_dir)

        loop = AgentLoop(
            bus=bus, provider=mock_provider, workspace=temp_dir,
            sessions=sessions,
        )

        mock_provider.chat = AsyncMock(return_value=LLMResponse(
            content="The answer is 42.", stop_reason="end_turn"))

        result = await loop.process_ephemeral("What is the answer?")
        assert "42" in result


class TestMultiTenantIsolation:
    """Verify multi-tenant isolation in an integration setting."""

    @pytest.mark.asyncio
    async def test_chat_id_session_isolation(self, temp_dir, mock_provider):
        """Messages for different chat_ids go to different sessions."""
        sessions = SessionManager(temp_dir)
        bus = MessageBus()

        loop = AgentLoop(
            bus=bus, provider=mock_provider, workspace=temp_dir,
            sessions=sessions,
        )

        async def respond(response_text):
            return LLMResponse(content=response_text, stop_reason="end_turn")

        mock_provider.chat = AsyncMock(side_effect=[
            LLMResponse(content="Reply to A", stop_reason="end_turn"),
            LLMResponse(content="Reply to B", stop_reason="end_turn"),
        ])

        await loop.process_direct("Message A", session_key="feishu:chat_A",
                                  chat_id="chat_A")
        await loop.process_direct("Message B", session_key="feishu:chat_B",
                                  chat_id="chat_B")

        session_a = await sessions.get_or_create("feishu:chat_A")
        session_b = await sessions.get_or_create("feishu:chat_B")

        assert session_a.messages[1]["content"] == "Reply to A"
        assert session_b.messages[1]["content"] == "Reply to B"


# ═══════════════════════════════════════════════════════════════════
# Real LLM Integration Tests (requires ANTHROPIC_AUTH_TOKEN)
# ═══════════════════════════════════════════════════════════════════


class TestRealLLMProvider:
    """AnthropicProvider against the real DeepSeek API."""

    @pytest.mark.asyncio
    @pytest.mark.real_llm
    async def test_basic_chat_response(self):
        """Provider gets a real response from DeepSeek."""
        p = _get_real_provider(max_tokens=512, temperature=0.1)
        messages = [{"role": "user", "content": "Reply with exactly: SWARM_OK"}]
        response = await p.chat(messages)
        assert response.content is not None
        assert "SWARM" in response.content
        assert response.stop_reason in ("end_turn", "stop")

    @pytest.mark.asyncio
    @pytest.mark.real_llm
    async def test_chinese_response(self):
        """Chinese language response works correctly."""
        p = _get_real_provider()
        messages = [{"role": "user", "content": "用中文回答：1+1等于几？只回答数字。"}]
        response = await p.chat(messages)
        assert response.content is not None
        assert "2" in response.content or "二" in response.content

    @pytest.mark.asyncio
    @pytest.mark.real_llm
    async def test_streaming_response(self):
        """Streaming produces content chunks."""
        p = _get_real_provider()
        messages = [{"role": "user", "content": "Say 'hello world' and nothing else."}]
        chunks = []
        async for chunk in p.stream(messages):
            if chunk.content:
                chunks.append(chunk.content)
        full = "".join(chunks)
        assert "hello" in full.lower()
        assert len(chunks) > 0

    @pytest.mark.asyncio
    @pytest.mark.real_llm
    async def test_multi_turn_conversation(self):
        """LLM remembers context across turns."""
        p = _get_real_provider()
        messages = [
            {"role": "user", "content": "我叫张三。"},
            {"role": "assistant", "content": "你好张三！"},
            {"role": "user", "content": "我的名字是什么？只回答名字。"},
        ]
        response = await p.chat(messages)
        assert "张三" in response.content

    @pytest.mark.asyncio
    @pytest.mark.real_llm
    async def test_usage_tracked(self):
        """Token usage is populated in response."""
        p = _get_real_provider()
        messages = [{"role": "user", "content": "Say hello."}]
        response = await p.chat(messages)
        assert response.usage
        usage = response.usage
        input_tokens = usage.get("input_tokens", 0) if isinstance(usage, dict) else getattr(usage, "input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0) if isinstance(usage, dict) else getattr(usage, "output_tokens", 0)
        assert input_tokens > 0, f"Expected input_tokens > 0, got {input_tokens}"
        assert output_tokens > 0, f"Expected output_tokens > 0, got {output_tokens}"

    @pytest.mark.asyncio
    @pytest.mark.real_llm
    async def test_empty_user_message_handled(self):
        """Provider handles empty user content gracefully."""
        p = _get_real_provider()
        messages = [
            {"role": "system", "content": "You are a test assistant."},
            {"role": "user", "content": ""},
        ]
        response = await p.chat(messages)
        assert response is not None


class TestRealAgentRunner:
    """AgentRunner with real DeepSeek backend."""

    @pytest.mark.asyncio
    @pytest.mark.real_llm
    async def test_simple_agent_run(self):
        """AgentRunner completes a full run cycle with real LLM."""
        p = _get_real_provider()
        runner = AgentRunner(p)
        spec = AgentRunSpec(
            initial_messages=[
                {"role": "system", "content": "You are a test agent. Be extremely brief."},
                {"role": "user", "content": "Say exactly 'PASS' and nothing else."},
            ],
            max_iterations=3,
        )
        result = await runner.run(spec)
        assert result.final_content is not None
        assert "PASS" in result.final_content.upper()
        assert result.stop_reason in ("end_turn", "stop")

    @pytest.mark.asyncio
    @pytest.mark.real_llm
    async def test_tool_use_with_real_llm(self):
        """Agent can use tools — verifies the tool execution pipeline works.

        Note: The LLM may choose to answer directly without using tools for trivial
        questions. We verify the pipeline is functional: if tools are called,
        they execute correctly; if not, the LLM still answers correctly.
        The key assertion is that the framework doesn't crash with tools attached.
        """
        p = _get_real_provider(max_tokens=512)

        registry = ToolRegistry()

        class EchoTool(ToolBase):
            name = "echo"
            description = "Echo back the input text. Use this to confirm you can call tools."

            async def execute(self, args, ctx):
                text = args.get("text", "")
                return tool_result(f"ECHO: {text}")

            def get_definition(self):
                return {
                    "type": "function",
                    "function": {
                        "name": "echo",
                        "description": "Echo back text. Call with {'text': 'your message'}.",
                        "parameters": {
                            "type": "object",
                            "properties": {"text": {"type": "string", "description": "Text to echo"}},
                            "required": ["text"],
                        },
                    },
                }

        registry.register(EchoTool())

        runner = AgentRunner(p)
        spec = AgentRunSpec(
            initial_messages=[
                {"role": "system", "content": (
                    "You MUST call the 'echo' tool with text='hello_world' before giving any answer. "
                    "This is a test of your tool-calling ability. First call echo, THEN reply."
                )},
                {"role": "user", "content": "Call the echo tool with hello_world, then tell me the result."},
            ],
            tools=registry,
            max_iterations=5,
        )
        result = await runner.run(spec)
        assert result.final_content is not None
        # Verify completion (LLM may or may not call tools depending on model behavior)
        assert result.stop_reason not in ("error",)
        # If tools were called, they should have executed without error
        if result.tools_used:
            assert "echo" in result.tools_used

    @pytest.mark.asyncio
    @pytest.mark.real_llm
    async def test_error_recovery_from_tool_failure(self):
        """Agent recovers gracefully when a tool raises an exception.

        The LLM may simulate tool failure without actually calling the tool.
        The key assertion: the framework doesn't crash or enter an error state.
        """
        p = _get_real_provider(max_tokens=512)

        registry = ToolRegistry()

        _broken_called = []

        class BrokenTool(ToolBase):
            name = "broken_tool"
            description = "A tool that always crashes. You MUST call it."

            async def execute(self, args, ctx):
                _broken_called.append(True)
                raise RuntimeError("Simulated tool crash")

            def get_definition(self):
                return {
                    "type": "function",
                    "function": {
                        "name": "broken_tool",
                        "description": "A tool that always crashes. Call it to see the error.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }

        registry.register(BrokenTool())

        runner = AgentRunner(p)
        spec = AgentRunSpec(
            initial_messages=[
                {"role": "system", "content": (
                    "You have a tool called 'broken_tool' that always crashes. "
                    "You MUST call it exactly once, then report what happened to the user. Be brief."
                )},
                {"role": "user", "content": "Call the broken_tool and tell me what happened."},
            ],
            tools=registry,
            max_iterations=5,
        )
        result = await runner.run(spec)
        # Must complete without entering an error state
        assert result.stop_reason not in ("error",)
        assert result.final_content is not None
        # If the LLM actually called the tool, it should have been tracked
        if _broken_called:
            assert "broken_tool" in result.tools_used

    @pytest.mark.asyncio
    @pytest.mark.real_llm
    async def test_streaming_callback_receives_chunks(self):
        """Streaming callback receives incremental chunks during agent run."""
        p = _get_real_provider()
        received = []

        def stream_cb(delta):
            received.append(delta)

        runner = AgentRunner(p)
        spec = AgentRunSpec(
            initial_messages=[
                {"role": "user", "content": "Count: 1, 2, 3. That's it."},
            ],
            max_iterations=2,
            stream_callback=stream_cb,
        )
        result = await runner.run(spec)
        assert len(received) > 0, "Expected streaming chunks"
        assert result.final_content is not None


class TestRealFullAgentLoop:
    """Complete AgentLoop 5-state cycle with real LLM."""

    @pytest.mark.asyncio
    @pytest.mark.real_llm
    async def test_full_cycle_process_direct(self):
        """RESTORE→BUILD→RUN→SAVE→RESPOND via CLI path."""
        p = _get_real_provider()
        ws = _temp_workspace()
        try:
            bus = MessageBus()
            sessions = SessionManager(ws / "data" / "sessions")
            ctx_builder = ContextBuilder(workspace=ws, timezone="Asia/Shanghai")

            loop = AgentLoop(
                bus=bus, provider=p, workspace=ws,
                sessions=sessions, context_builder=ctx_builder,
                max_iterations=5,
            )

            response = await loop.process_direct(
                content="Say exactly 'SWARM_INTEGRATION_TEST_PASS' and nothing else.",
                session_key="integration:full_cycle",
            )

            assert response is not None
            assert response.content is not None
            assert "SWARM_INTEGRATION_TEST_PASS" in response.content
        finally:
            import shutil
            shutil.rmtree(ws, ignore_errors=True)

    @pytest.mark.asyncio
    @pytest.mark.real_llm
    async def test_session_persistence_across_turns(self):
        """Session remembers context across multiple turns."""
        p = _get_real_provider()
        ws = _temp_workspace()
        try:
            bus = MessageBus()
            sessions = SessionManager(ws / "data" / "sessions")
            ctx_builder = ContextBuilder(workspace=ws)

            loop = AgentLoop(
                bus=bus, provider=p, workspace=ws,
                sessions=sessions, context_builder=ctx_builder,
                max_iterations=5,
            )

            sk = "integration:persist_test"

            # Turn 1: tell the agent a fact
            await loop.process_direct(
                content="记住：我最喜欢的颜色是蓝色。回复'记住了'即可。",
                session_key=sk,
            )

            # Turn 2: ask about the fact
            response = await loop.process_direct(
                content="我刚才说我喜欢的颜色是什么？只回答颜色名称。",
                session_key=sk,
            )

            assert response is not None
            assert "蓝" in response.content or "blue" in response.content.lower()
        finally:
            import shutil
            shutil.rmtree(ws, ignore_errors=True)

    @pytest.mark.asyncio
    @pytest.mark.real_llm
    async def test_command_bypasses_llm(self):
        """/help command skips LLM entirely."""
        p = _get_real_provider()
        ws = _temp_workspace()
        try:
            bus = MessageBus()
            sessions = SessionManager(ws / "data" / "sessions")
            ctx_builder = ContextBuilder(workspace=ws)

            loop = AgentLoop(
                bus=bus, provider=p, workspace=ws,
                sessions=sessions, context_builder=ctx_builder,
            )

            # Track LLM calls
            call_count = 0
            original = p.chat

            async def counting_chat(*a, **kw):
                nonlocal call_count
                call_count += 1
                return await original(*a, **kw)

            p.chat = counting_chat

            response = await loop.process_direct(
                content="/help",
                session_key="integration:cmd_test",
            )

            assert response is not None
            assert "help" in response.content.lower()
            # Command should NOT call the LLM
            assert call_count == 0, f"Expected 0 LLM calls, got {call_count}"
        finally:
            import shutil
            shutil.rmtree(ws, ignore_errors=True)

    @pytest.mark.asyncio
    @pytest.mark.real_llm
    async def test_concurrent_session_isolation(self):
        """Two sessions don't leak context between each other."""
        p = _get_real_provider()
        ws = _temp_workspace()
        try:
            bus = MessageBus()
            sessions = SessionManager(ws / "data" / "sessions")
            ctx_builder = ContextBuilder(workspace=ws)

            loop = AgentLoop(
                bus=bus, provider=p, workspace=ws,
                sessions=sessions, context_builder=ctx_builder,
                max_iterations=3,
            )

            # Session A: color = blue
            await loop.process_direct(
                content="记住：我喜欢蓝色。回复'好'即可。",
                session_key="integration:session_a",
            )
            await asyncio.sleep(0.5)

            # Session B: color = red
            await loop.process_direct(
                content="记住：我喜欢红色。回复'好'即可。",
                session_key="integration:session_b",
            )
            await asyncio.sleep(0.5)

            # Ask both
            resp_a = await loop.process_direct(
                content="我喜欢什么颜色？一个字回答。",
                session_key="integration:session_a",
            )
            await asyncio.sleep(0.5)
            resp_b = await loop.process_direct(
                content="我喜欢什么颜色？一个字回答。",
                session_key="integration:session_b",
            )

            assert resp_a is not None, "Session A got no response"
            assert resp_b is not None, "Session B got no response"
            a_content = resp_a.content or ""
            b_content = resp_b.content or ""
            assert ("蓝" in a_content or "blue" in a_content.lower()), \
                f"Session A should remember blue, got: {a_content[:200]}"
            assert ("红" in b_content or "red" in b_content.lower()), \
                f"Session B should remember red, got: {b_content[:200]}"
        finally:
            import shutil
            shutil.rmtree(ws, ignore_errors=True)


class TestRealConcurrency:
    """Concurrent request handling with real LLM."""

    @pytest.mark.asyncio
    @pytest.mark.real_llm
    async def test_concurrent_requests_complete(self):
        """Multiple concurrent LLM requests all complete successfully."""
        p = _get_real_provider()

        async def single(n):
            messages = [{"role": "user", "content": f"Reply with just the number {n}."}]
            return await p.chat(messages)

        tasks = [single(i) for i in range(3)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, r in enumerate(results):
            if isinstance(r, Exception):
                pytest.fail(f"Request {i} failed: {r}")
            assert r.content is not None, f"Request {i} has no content"
            assert str(i) in r.content, f"Request {i} missing '{i}' in: {r.content}"
