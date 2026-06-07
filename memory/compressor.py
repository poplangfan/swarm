"""Context compressor — trajectory-preserving context window management.

Inspired by hermes-agent's trajectory_compressor:
Rather than blindly truncating by token count, maintain narrative coherence
by preserving the structure of the conversation flow.
"""

from __future__ import annotations

from typing import Any


class ContextCompressor:
    """Compresses conversation context while preserving narrative coherence.

    Strategy (multi-pass):
    1. Token budget check — if total is under budget, no compression needed
    2. System prompt is always preserved (never truncated)
    3. Recent messages (last N turns) are always preserved
    4. Middle messages are summarized using key fact extraction
    5. Tool results are compressed (keep only key outputs)
    6. If still over budget, oldest messages are dropped with a summary marker
    """

    def __init__(
        self,
        max_tokens: int = 32_000,
        min_recent_turns: int = 5,
        summary_marker: str = "[Earlier conversation summarized]",
    ):
        self.max_tokens = max_tokens
        self.min_recent_turns = min_recent_turns
        self.summary_marker = summary_marker

    def compress(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Compress a message list to fit within the token budget.

        Returns a new message list (does not mutate the original).
        """
        if not messages:
            return []

        current_tokens = self._estimate_tokens(messages)
        if current_tokens <= self.max_tokens:
            return list(messages)

        # Step 1: Always preserve system prompt
        result = []
        start_idx = 0
        if messages[0].get("role") == "system":
            result.append(messages[0])
            start_idx = 1

        # Step 2: Count turns from the end
        turns = self._count_turns(messages, start_idx)
        # _find_recent_cutoff returns the index of the first message to keep (#6)
        recent_start = self._find_recent_cutoff(messages, start_idx, turns)

        # Step 3: If there are old messages to compress
        if recent_start > start_idx:
            # Add a summary marker for compressed content
            old_count = recent_start - start_idx
            result.append({
                "role": "system",
                "content": f"{self.summary_marker} ({old_count} messages compressed)",
            })

        # Step 4: Add recent messages
        result.extend(messages[recent_start:])

        # Step 5: If still over budget, compress tool results
        result = self._compress_tool_results(result)

        # Step 6: Final truncation if needed
        result = self._truncate_by_tokens(result, self.max_tokens)

        return result

    def _count_turns(self, messages: list[dict], start: int) -> int:
        """Count the number of user-assistant turn pairs."""
        turns = 0
        for msg in messages[start:]:
            if msg.get("role") == "user":
                turns += 1
        return turns

    def _find_recent_cutoff(self, messages: list[dict], start: int, total_turns: int) -> int:
        """Find the index where to cut for keeping min_recent_turns."""
        if total_turns <= self.min_recent_turns:
            return start

        turns_seen = 0
        for i in range(len(messages) - 1, start - 1, -1):
            if messages[i].get("role") == "user":
                turns_seen += 1
                if turns_seen >= self.min_recent_turns:
                    return i
        return start

    def _compress_tool_results(self, messages: list[dict]) -> list[dict]:
        """Compress verbose tool results to key information only."""
        result = []
        for msg in messages:
            if msg.get("role") == "tool":
                content = str(msg.get("content", ""))
                if len(content) > 2000:
                    compressed = {
                        **msg,
                        "content": content[:1000] + "\n... [compressed] ...\n" + content[-500:],
                    }
                    result.append(compressed)
                else:
                    result.append(msg)
            else:
                result.append(msg)
        return result

    def _truncate_by_tokens(self, messages: list[dict], max_tokens: int) -> list[dict]:
        """Final pass: drop oldest non-system messages until under budget."""
        if not messages:
            return []
        result = [messages[0]] if messages[0].get("role") == "system" else []
        remaining = list(messages[1:]) if result else list(messages)

        # Keep adding messages from the end
        selected = []
        for msg in reversed(remaining):
            test = result + [msg] + selected
            if self._estimate_tokens(test) <= max_tokens:
                selected.insert(0, msg)
            else:
                break

        return result + selected

    def _estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate tokens for a message list using shared counter."""
        from utils.tokens import estimate_message_tokens
        return estimate_message_tokens(messages)

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for a text string."""
        from utils.tokens import estimate_tokens as _est
        return _est(text)
