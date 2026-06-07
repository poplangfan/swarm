"""Token counting: tiktoken-based exact count with estimation fallback."""

from __future__ import annotations

from typing import Any

from swarm.utils.tokens import estimate_tokens


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
        if self._encoder:
            return len(self._encoder.encode(text))
        return self.estimate(text)

    def estimate(self, text: str) -> int:
        return estimate_tokens(text)

    def estimate_messages(self, messages: list[dict[str, Any]]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        total += self.estimate(block.get("text", ""))
            total += 4
        return total
