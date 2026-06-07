"""Deep tests for providers — retry, fallback, token counting edge cases."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from swarm.providers.base import LLMResponse, StreamChunk
from swarm.providers.retry import RetryConfig, async_retry
from swarm.providers.fallback import FallbackProvider
from swarm.providers.token_counter import TokenCounter
from swarm.providers.factory import make_provider
from swarm.config.schema import LLMConfig


class TestRetryMechanism:
    @pytest.mark.asyncio
    async def test_retry_count_exact(self):
        call_counts = []

        @async_retry(RetryConfig(max_retries=3, base_delay=0.001))
        async def flaky():
            call_counts.append(1)
            if len(call_counts) < 3:
                raise ConnectionError("not yet")
            return "success"

        result = await flaky()
        assert result == "success"
        assert len(call_counts) == 3

    @pytest.mark.asyncio
    async def test_exhausted_retries(self):
        @async_retry(RetryConfig(max_retries=2, base_delay=0.001))
        async def always_fails():
            raise RuntimeError("permanent error")

        with pytest.raises(RuntimeError, match="permanent error"):
            await always_fails()

    @pytest.mark.asyncio
    async def test_no_jitter(self):
        call_times = []

        @async_retry(RetryConfig(max_retries=2, base_delay=0.01, jitter=False))
        async def flaky():
            call_times.append(asyncio.get_event_loop().time())
            if len(call_times) < 3:
                raise ConnectionError("fail")
            return "ok"

        await flaky()
        assert len(call_times) == 3

    @pytest.mark.asyncio
    async def test_custom_config(self):
        config = RetryConfig(max_retries=5, base_delay=0.001, max_delay=0.1)
        calls = 0

        @async_retry(config)
        async def succeed_after_4():
            nonlocal calls
            calls += 1
            if calls < 5:
                raise ConnectionError()
            return "done"

        result = await succeed_after_4()
        assert result == "done"
        assert calls == 5


class TestFallbackProvider:
    @pytest.mark.asyncio
    async def test_primary_succeeds(self):
        primary = MagicMock()
        primary.chat = AsyncMock(return_value=LLMResponse(
            content="from primary", stop_reason="end_turn"))
        secondary = MagicMock()
        fallback = FallbackProvider([primary, secondary])

        response = await fallback.chat([{"role": "user", "content": "hi"}])
        assert response.content == "from primary"
        secondary.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_to_secondary(self):
        primary = MagicMock()
        primary.chat = AsyncMock(side_effect=ConnectionError("primary down"))
        secondary = MagicMock()
        secondary.chat = AsyncMock(return_value=LLMResponse(
            content="from secondary", stop_reason="end_turn"))
        fallback = FallbackProvider([primary, secondary])

        response = await fallback.chat([{"role": "user", "content": "hi"}])
        assert response.content == "from secondary"

    @pytest.mark.asyncio
    async def test_all_providers_fail(self):
        p1 = MagicMock()
        p1.chat = AsyncMock(side_effect=ConnectionError("p1 down"))
        p2 = MagicMock()
        p2.chat = AsyncMock(side_effect=ConnectionError("p2 down"))
        fallback = FallbackProvider([p1, p2])

        with pytest.raises(ConnectionError, match="p2 down"):
            await fallback.chat([{"role": "user", "content": "hi"}])


class TestTokenCounter:
    def test_with_tiktoken(self):
        counter = TokenCounter(model="gpt-4o")
        tokens = counter.estimate("Hello, world!")
        assert tokens > 0

    def test_empty_text(self):
        counter = TokenCounter()
        assert counter.estimate("") == 0
        assert counter.count("") == 0

    def test_estimate_messages(self):
        counter = TokenCounter()
        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        tokens = counter.estimate_messages(msgs)
        assert tokens > 10

    def test_multimodal_content(self):
        counter = TokenCounter()
        msgs = [
            {"role": "user", "content": [
                {"type": "text", "text": "What's in this image?"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc123"}},
            ]},
        ]
        tokens = counter.estimate_messages(msgs)
        assert tokens > 5

    def test_claude_model(self):
        counter = TokenCounter(model="claude-sonnet-4-6")
        # Should fall back to estimation for Claude
        tokens = counter.count("Hello world this is a longer test sentence")
        assert tokens > 0


class TestMakeProvider:
    def test_creates_openai_provider(self):
        import os
        # Clear proxy env vars that break httpx
        for k in list(os.environ.keys()):
            if 'proxy' in k.lower():
                os.environ.pop(k, None)
        config = LLMConfig(provider="openai", api_key="sk-test",
                          base_url="https://api.openai.com/v1")
        # Import after clearing env
        from swarm.providers.openai_compat import OpenAICompatProvider
        provider = make_provider(config)
        assert isinstance(provider, OpenAICompatProvider)

    def test_creates_anthropic_provider(self):
        config = LLMConfig(provider="anthropic", api_key="sk-test",
                          base_url="https://api.deepseek.com/anthropic")
        from swarm.providers.anthropic import AnthropicProvider
        provider = make_provider(config)
        assert isinstance(provider, AnthropicProvider)

    def test_custom_treated_as_openai(self):
        import os
        for k in list(os.environ.keys()):
            if 'proxy' in k.lower():
                os.environ.pop(k, None)
        config = LLMConfig(provider="custom", api_key="sk-test",
                          base_url="http://localhost:8000/v1")
        from swarm.providers.openai_compat import OpenAICompatProvider
        provider = make_provider(config)
        assert isinstance(provider, OpenAICompatProvider)

    def test_unknown_provider_raises(self):
        # Unknown provider should be caught by Pydantic validation first
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            LLMConfig(provider="unknown_provider", api_key="sk-test",
                     base_url="http://localhost:8000/v1")
