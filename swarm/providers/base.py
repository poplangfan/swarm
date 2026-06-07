"""Abstract LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class StreamChunk:
    """A single chunk from a streaming response."""
    content: str | None = None
    tool_call_delta: dict | None = None
    finish_reason: str | None = None
    usage: dict | None = None
    reasoning_content: str | None = None


@dataclass
class LLMResponse:
    """Complete LLM response after streaming or non-streaming call."""
    content: str | None
    stop_reason: str
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    reasoning_content: str | None = None

    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    def __init__(self, api_key: str, model: str, **kwargs):
        self.api_key = api_key
        self.model = model
        self._max_tokens = kwargs.get("max_tokens", 4096)

    @property
    def generation(self):
        if not hasattr(self, '_generation_cache'):
            class _Gen:
                max_tokens = self._max_tokens
            self._generation_cache = _Gen()
        return self._generation_cache

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> LLMResponse:
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        ...

    def count_tokens(self, text: str) -> int:
        from swarm.utils.tokens import estimate_tokens
        return estimate_tokens(text)

    @property
    def context_window(self) -> int:
        return 128_000
