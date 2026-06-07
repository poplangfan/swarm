"""Shared token estimation — single source of truth for all modules.

All token counting across the framework delegates to this module's functions.
For exact counting, use TokenCounter (tiktoken-based). For fast estimation,
use estimate_tokens() which provides the standard chars/4 heuristic.
"""

from __future__ import annotations

from typing import Any

# Lazy-initialized singleton TokenCounter
_counter: TokenCounter | None = None


class TokenCounter:
    """Token counter using tiktoken when available, estimation otherwise."""

    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self._encoder = None
        try:
            import tiktoken
            _CL100K_MODELS = ("gpt-4", "gpt-4o", "gpt-3.5", "text-embedding", "o1", "o3")
            if any(x in model for x in _CL100K_MODELS):
                self._encoder = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            pass

    def count(self, text: str) -> int:
        """Exact count using tiktoken if available, else estimate."""
        if self._encoder:
            return len(self._encoder.encode(text))
        return _estimate(text)

    def count_messages(self, messages: list[dict[str, Any]]) -> int:
        """Estimate total tokens across a message list."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += _estimate(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        total += _estimate(block.get("text", ""))
            total += 4  # message framing overhead
        return total


def estimate_tokens(text: str) -> int:
    """Fast token estimation: ~4 chars per token (works for CJK and Latin)."""
    return _estimate(text)


def estimate_message_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate total tokens for a list of messages including overhead."""
    return _get_counter().count_messages(messages)


def _estimate(text: str) -> int:
    """Core estimation: max(1, len // 4)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _get_counter() -> TokenCounter:
    """Get or create the singleton counter."""
    global _counter
    if _counter is None:
        _counter = TokenCounter()
    return _counter
