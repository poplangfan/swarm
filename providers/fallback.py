"""Fallback provider chain: try primary, fall through to backups on failure."""

from __future__ import annotations

import structlog

from providers.base import LLMProvider, LLMResponse

logger = structlog.get_logger(__name__)


class FallbackProvider(LLMProvider):
    """Composite provider that falls back through a chain on failure."""

    def __init__(self, providers: list[LLMProvider]):
        self._providers = providers
        super().__init__(api_key="", model=providers[0].model if providers else "")

    @property
    def context_window(self) -> int:
        """Return the minimum context window across all providers in the chain."""
        if not self._providers:
            return 128_000
        return min(getattr(p, 'context_window', 128_000) for p in self._providers)

    async def chat(self, messages, tools=None, **kwargs) -> LLMResponse:
        last_error = None
        for i, provider in enumerate(self._providers):
            try:
                return await provider.chat(messages, tools=tools, **kwargs)
            except Exception as e:
                last_error = e
                if i < len(self._providers) - 1:
                    logger.warning(
                        "provider_fallback",
                        from_provider=type(provider).__name__,
                        to_provider=type(self._providers[i + 1]).__name__,
                        error=str(e),
                    )
        raise last_error or RuntimeError("All providers failed")

    async def stream(self, messages, tools=None, **kwargs):
        for i, provider in enumerate(self._providers):
            try:
                async for chunk in provider.stream(messages, tools=tools, **kwargs):
                    yield chunk
                return
            except Exception as e:
                if i < len(self._providers) - 1:
                    logger.warning(
                        "provider_fallback",
                        from_provider=type(provider).__name__,
                        to_provider=type(self._providers[i + 1]).__name__,
                        error=str(e),
                        mode="stream",
                    )
                    continue
                raise
