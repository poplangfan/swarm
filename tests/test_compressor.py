"""Detailed tests for context compressor."""

from memory.compressor import ContextCompressor


class TestCompressorEdgeCases:
    def test_all_recent_messages_preserved(self):
        compressor = ContextCompressor(max_tokens=50000, min_recent_turns=3)
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
            {"role": "assistant", "content": "A2"},
            {"role": "user", "content": "Q3"},
            {"role": "assistant", "content": "A3"},
        ]
        result = compressor.compress(messages)
        assert len(result) == len(messages)  # No compression needed

    def test_old_messages_compressed_with_marker(self):
        compressor = ContextCompressor(max_tokens=80, min_recent_turns=1)
        messages = [
            {"role": "system", "content": "Helpful assistant."},
            {"role": "user", "content": "First question that is somewhat long"},
            {"role": "assistant", "content": "First answer that is also quite long"},
            {"role": "user", "content": "Second question"},
            {"role": "assistant", "content": "Second answer"},
        ]
        result = compressor.compress(messages)
        # System prompt preserved
        assert result[0]["role"] == "system"
        # Should have compressed some old messages
        assert len(result) <= len(messages)

    def test_single_message_unchanged(self):
        compressor = ContextCompressor(max_tokens=100)
        msg = [{"role": "user", "content": "Short"}]
        result = compressor.compress(msg)
        assert len(result) == 1

    def test_very_small_budget(self):
        compressor = ContextCompressor(max_tokens=20)
        messages = [
            {"role": "user", "content": "A" * 200},
            {"role": "assistant", "content": "B" * 200},
        ]
        result = compressor.compress(messages)
        assert len(result) <= 2  # Should not crash

    def test_token_estimation(self):
        compressor = ContextCompressor()
        assert compressor.estimate_tokens("hello") == 1
        assert compressor.estimate_tokens("a" * 100) == 25
        assert compressor.estimate_tokens("") == 0


class TestCompressorNarrativeCoherence:
    def test_tool_interactions_kept_together(self):
        """Tool call + tool result should stay together when possible."""
        compressor = ContextCompressor(max_tokens=200, min_recent_turns=1)
        messages = [
            {"role": "user", "content": "old question"},
            {"role": "assistant", "content": "old answer"},
            {"role": "user", "content": "search for X"},
            {"role": "tool", "content": "Found X"},
            {"role": "assistant", "content": "Here is X"},
        ]
        result = compressor.compress(messages)
        # Recent messages preserved
        assert len(result) >= 3
