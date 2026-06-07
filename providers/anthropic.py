"""Anthropic provider — supports Claude, DeepSeek (Anthropic-compat), and custom.

Features:
- Native Anthropic Messages API support
- DeepSeek Anthropic-compatible endpoint support
- Streaming response collection (non-streaming use)
- Tool use conversion (Anthropic ↔ OpenAI format)
- System prompt extraction from messages
- Retry with exponential backoff
- Context window awareness
- Token usage tracking
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import structlog

from providers.base import LLMProvider, LLMResponse, StreamChunk
from providers.retry import RetryConfig, async_retry

logger = structlog.get_logger(__name__)


class AnthropicProvider(LLMProvider):
    """Provider for Anthropic Claude models and DeepSeek's Anthropic-compatible API.

    Uses the native Anthropic Messages API (not OpenAI-compatible).
    Handles tool use conversion between Anthropic's native format and
    the OpenAI-style format used internally by Swarm.

    Context windows (known models):
    - claude-opus-4-8: 200,000
    - claude-sonnet-4-6: 200,000
    - deepseek-v4-pro: 128,000
    """

    _KNOWN_CONTEXT_WINDOWS = {
        "claude-opus-4-8": 200_000,
        "claude-sonnet-4-6": 200_000,
        "claude-haiku-4-5": 200_000,
        "deepseek-v4-pro": 128_000,
        "deepseek-v3": 128_000,
    }

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ):
        super().__init__(api_key=api_key, model=model, max_tokens=max_tokens)
        self._base_url = base_url
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = None
        self._extra_headers = kwargs.get("extra_headers", {})

    @property
    def context_window(self) -> int:
        """Return the known context window size for this model."""
        return self._KNOWN_CONTEXT_WINDOWS.get(
            self.model,
            128_000,  # Default assumption
        )

    def _get_client(self):
        """Lazy-initialize the AsyncAnthropic client."""
        if self._client is None:
            from anthropic import AsyncAnthropic

            client_kwargs = {"api_key": self.api_key}
            if self._base_url:
                client_kwargs["base_url"] = self._base_url
            if self._extra_headers:
                client_kwargs["default_headers"] = self._extra_headers

            self._client = AsyncAnthropic(**client_kwargs)
        return self._client

    # ── Message / Tool Conversion (shared by chat + stream) ──────

    def _convert_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Convert OpenAI-format messages to Anthropic format.

        Returns (system_prompt, anthropic_messages).
        """
        system_prompt = ""
        anthropic_messages: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_prompt = content if isinstance(content, str) else str(content)
            elif role == "user":
                anthropic_messages.append(
                    {"role": "user", "content": self._convert_content(content)}
                )
            elif role == "assistant":
                text = content if isinstance(content, str) else (content or "")
                if "tool_calls" in msg:
                    # Merge text with tool_use blocks — preserve both (#6)
                    blocks: list[dict[str, Any]] = []
                    if text:
                        blocks.append({"type": "text", "text": text})
                    for tc in msg["tool_calls"]:
                        args = tc["function"]["arguments"]
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                pass
                        blocks.append(
                            {
                                "type": "tool_use",
                                "id": tc["id"],
                                "name": tc["function"]["name"],
                                "input": args,
                            }
                        )
                    anthropic_messages.append({"role": "assistant", "content": blocks})
                else:
                    anthropic_messages.append({"role": "assistant", "content": text})
            elif role == "tool":
                # Use Anthropic native tool_result content block (#3)
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.get("tool_call_id", ""),
                                "content": content,
                            }
                        ],
                    }
                )
        return system_prompt, anthropic_messages

    @staticmethod
    def _convert_tools(
        tools: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]] | None:
        """Convert OpenAI tool definitions to Anthropic format."""
        if not tools:
            return None
        return [
            {
                "name": t["function"]["name"],
                "description": t["function"].get("description", ""),
                "input_schema": t["function"].get(
                    "parameters",
                    {"type": "object", "properties": {}, "required": []},
                ),
            }
            for t in tools
        ]

    # ── API Methods ──────────────────────────────────────────────

    @async_retry(RetryConfig(max_retries=3, base_delay=1.0))
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> LLMResponse:
        """Send a chat request and return a complete response.

        Converts OpenAI-format messages and tools to Anthropic format,
        then converts the response back.
        """
        client = self._get_client()

        system_prompt, anthropic_messages = self._convert_messages(messages)
        anthropic_tools = self._convert_tools(tools)

        # Remove kwargs that Anthropic doesn't accept
        kwargs.pop("temperature", None)
        kwargs.pop("max_tokens", None)

        response = await client.messages.create(
            model=self.model,
            system=system_prompt or "You are a helpful assistant named Swarm.",
            messages=anthropic_messages,
            tools=anthropic_tools,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            **kwargs,
        )

        # Convert response back to standard format
        text_content = ""
        tool_calls = []
        usage_dict = {}

        for block in response.content:
            if block.type == "text":
                text_content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "function": {
                            "name": block.name,
                            "arguments": (
                                block.input
                                if isinstance(block.input, str)
                                else self._serialize_json(block.input)
                            ),
                        },
                    }
                )

        # Extract usage
        if hasattr(response, "usage") and response.usage:
            usage_dict = {
                "input_tokens": getattr(response.usage, "input_tokens", 0),
                "output_tokens": getattr(response.usage, "output_tokens", 0),
            }

        # Check stop reason
        stop_reason = getattr(response, "stop_reason", "end_turn")
        if tool_calls:
            stop_reason = "tool_calls"

        return LLMResponse(
            content=text_content or None,
            stop_reason=stop_reason,
            tool_calls=tool_calls,
            usage=usage_dict,
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """Stream response chunks with full event handling.

        Uses the Anthropic SDK's event-level streaming to capture
        text_delta, input_json_delta (tool use), and tool_use block starts.
        """
        client = self._get_client()

        system_prompt, anthropic_messages = self._convert_messages(messages)
        anthropic_tools = self._convert_tools(tools)

        kwargs.pop("temperature", None)
        kwargs.pop("max_tokens", None)

        async with client.messages.stream(
            model=self.model,
            system=system_prompt or "You are a helpful assistant.",
            messages=anthropic_messages,
            tools=anthropic_tools,
            max_tokens=self._max_tokens,
            **kwargs,
        ) as stream:
            async for event in stream:
                # ── Content block start (tool_use name + id) ──
                if event.type == "content_block_start":
                    if event.content_block.type == "tool_use":
                        yield StreamChunk(
                            tool_call_delta={
                                "index": event.index,
                                "id": event.content_block.id,
                                "function": {"name": event.content_block.name},
                            }
                        )

                # ── Content block delta (text or tool args) ──
                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        yield StreamChunk(content=delta.text)
                    elif delta.type == "input_json_delta":
                        yield StreamChunk(
                            tool_call_delta={
                                "index": event.index,
                                "function": {"arguments": delta.partial_json},
                            }
                        )

                # ── Message delta (stop_reason + usage) ──
                elif event.type == "message_delta":
                    finish_reason = event.delta.stop_reason or "end_turn"
                    usage_dict = {}
                    if hasattr(event, "usage") and event.usage:
                        usage_dict = {
                            "input_tokens": getattr(event.usage, "input_tokens", 0),
                            "output_tokens": getattr(event.usage, "output_tokens", 0),
                        }
                    yield StreamChunk(finish_reason=finish_reason, usage=usage_dict)

    def _convert_content(self, content: Any) -> str | list[dict]:
        """Convert OpenAI-style content blocks to Anthropic format."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            blocks = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        blocks.append({"type": "text", "text": block.get("text", "")})
                    elif block.get("type") == "image_url":
                        url = block.get("image_url", {}).get("url", "")
                        if url.startswith("data:image/"):
                            try:
                                media_type = url.split(";")[0].replace("data:", "")
                                b64_data = url.split(",", 1)[1]
                                blocks.append(
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": media_type,
                                            "data": b64_data,
                                        },
                                    }
                                )
                            except (IndexError, ValueError):
                                logger.debug(
                                    "image_data_uri_parse_failed", url_preview=str(url)[:80]
                                )
            return blocks if blocks else str(content)
        return str(content)

    @staticmethod
    def _serialize_json(data: Any) -> str:
        """Serialize data to JSON string for tool call arguments."""
        try:
            return json.dumps(data, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(data)
