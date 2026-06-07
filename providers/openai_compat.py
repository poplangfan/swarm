"""OpenAI-compatible provider — supports OpenAI, vLLM, Ollama, and any OpenAI-compat API.

Features:
- Full OpenAI Chat Completions API support
- Streaming with incremental delta forwarding
- Tool call accumulation from streaming deltas
- Reasoning/thinking content extraction (DeepSeek-R1, o1)
- Structured output support (json_object, json_schema)
- Automatic retry with exponential backoff
- Token usage tracking
- Context window awareness per model
"""

from __future__ import annotations

from typing import Any, AsyncIterator

import json

import structlog
from openai import AsyncOpenAI

from providers.base import LLMProvider, LLMResponse, StreamChunk
from providers.retry import RetryConfig, async_retry

logger = structlog.get_logger(__name__)


class OpenAICompatProvider(LLMProvider):
    """Provider for OpenAI and any OpenAI-compatible API.

    Works with:
    - OpenAI (api.openai.com)
    - vLLM (localhost:8000)
    - Ollama (localhost:11434)
    - Any OpenAI-compatible endpoint

    Known context windows:
    - gpt-4o: 128,000
    - gpt-4o-mini: 128,000
    - gpt-4-turbo: 128,000
    - gpt-3.5-turbo: 16,384
    """

    _KNOWN_CONTEXT_WINDOWS = {
        "gpt-4o": 128_000,
        "gpt-4o-mini": 128_000,
        "gpt-4-turbo": 128_000,
        "gpt-4": 8_192,
        "gpt-3.5-turbo": 16_384,
    }

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ):
        super().__init__(api_key=api_key, model=model, max_tokens=max_tokens)
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._extra_body = kwargs.get("extra_body", None)
        # Disable stream_options for older vLLM/Ollama endpoints that reject it (#7)
        self._stream_options_enabled = kwargs.get("stream_options_enabled", True)

    @property
    def context_window(self) -> int:
        return self._KNOWN_CONTEXT_WINDOWS.get(self.model, 128_000)

    @async_retry(RetryConfig(max_retries=3))
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> LLMResponse:
        """Send a chat request and return a complete response."""
        # Build request parameters
        params: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.pop("temperature", self._temperature),
            "max_tokens": kwargs.pop("max_tokens", self._max_tokens),
        }

        if tools:
            params["tools"] = tools

        if self._extra_body:
            params["extra_body"] = self._extra_body

        params.update(kwargs)

        response = await self._client.chat.completions.create(**params)

        # Guard against empty choices (edge case: usage-only API responses)
        if not response.choices:
            logger.warning("empty_choices_in_response", model=self.model)
            return LLMResponse(
                content=None,
                stop_reason="end_turn",
                usage=response.usage.model_dump() if response.usage else {},
            )

        # Extract response data
        choice = response.choices[0]
        usage = response.usage.model_dump() if response.usage else {}

        # Handle tool calls
        if choice.finish_reason == "tool_calls" or (
            hasattr(choice.message, 'tool_calls') and choice.message.tool_calls
        ):
            return LLMResponse(
                content=choice.message.content,
                stop_reason="tool_calls",
                tool_calls=[
                    {
                        "id": tc.id,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in (choice.message.tool_calls or [])
                ],
                usage=usage,
            )

        # Handle reasoning/thinking content (DeepSeek-R1, o1 models)
        reasoning_content = getattr(choice.message, 'reasoning_content', None)

        # Handle refusal
        if choice.finish_reason == "content_filter":
            return LLMResponse(
                content="I'm unable to respond to that request.",
                stop_reason="content_filter",
                usage=usage,
            )

        # Handle length limit
        if choice.finish_reason == "length":
            return LLMResponse(
                content=choice.message.content,
                stop_reason="max_tokens",
                usage=usage,
                reasoning_content=reasoning_content,
            )

        # Normal completion
        return LLMResponse(
            content=choice.message.content,
            stop_reason="end_turn",
            usage=usage,
            reasoning_content=reasoning_content,
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """Stream response deltas from the API.

        Accumulates:
        - Text content (yielded as StreamChunk with content)
        - Tool call deltas (accumulated and yielded when complete)
        - Reasoning content (yielded as StreamChunk with reasoning_content)
        """
        params: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.pop("temperature", self._temperature),
            "max_tokens": kwargs.pop("max_tokens", self._max_tokens),
            "stream": True,
        }
        if self._stream_options_enabled:
            params["stream_options"] = {"include_usage": True}

        if tools:
            params["tools"] = tools

        params.update(kwargs)

        # Track tool call accumulation
        tool_call_buffers: dict[int, dict] = {}

        stream = await self._client.chat.completions.create(**params)
        async for chunk in stream:
            if not chunk.choices:
                # Usage-only chunk (stream_options)
                if hasattr(chunk, 'usage') and chunk.usage:
                    yield StreamChunk(usage=chunk.usage.model_dump())
                continue

            delta = chunk.choices[0].delta
            finish_reason = chunk.choices[0].finish_reason

            # Content delta
            if delta and delta.content:
                yield StreamChunk(
                    content=delta.content,
                    finish_reason=finish_reason,
                )

            # Reasoning content (DeepSeek-R1, o1)
            if delta and hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                yield StreamChunk(
                    reasoning_content=delta.reasoning_content,
                )

            # Tool call deltas
            if delta and delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_call_buffers:
                        tool_call_buffers[idx] = {
                            "id": tc_delta.id or "",
                            "function": {"name": "", "arguments": ""},
                        }
                    buf = tool_call_buffers[idx]
                    if tc_delta.id:
                        buf["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            buf["function"]["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            buf["function"]["arguments"] += tc_delta.function.arguments

                    yield StreamChunk(
                        tool_call_delta={
                            "index": idx,
                            "id": tc_delta.id,
                            "function": {
                                "name": tc_delta.function.name if tc_delta.function else None,
                                "arguments": tc_delta.function.arguments if tc_delta.function else None,
                            },
                        },
                    )

            # End of stream
            if finish_reason:
                yield StreamChunk(finish_reason=finish_reason)

    async def chat_with_structured_output(
        self,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any],
        strict: bool = True,
    ) -> dict[str, Any] | None:
        """Request structured JSON output using OpenAI's response_format.

        Args:
            messages: Chat messages
            json_schema: JSON Schema for the expected output
            strict: Whether to enforce strict schema compliance

        Returns:
            Parsed JSON dict, or None if parsing fails
        """
        try:
            params: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.0,  # Deterministic for structured output
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "structured_response",
                        "strict": strict,
                        "schema": json_schema,
                    },
                },
            }

            response = await self._client.chat.completions.create(**params)
            if not response.choices:
                return None
            content = response.choices[0].message.content
            if content:
                return json.loads(content)
        except json.JSONDecodeError:
            logger.warning("structured_output_parse_failed")
        except Exception:
            logger.exception("structured_output_api_error")
        return None
