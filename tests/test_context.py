"""Tests for ContextBuilder — system prompt assembly."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock
from swarm.agent.context import ContextBuilder, RequestContext


class TestContextBuilder:
    def test_builds_system_prompt(self):
        cb = ContextBuilder(workspace=Path("."))
        prompt = cb.build_system_prompt(channel="feishu", chat_id="oc_test")
        assert "Swarm" in prompt
        assert "feishu" in prompt.lower()
        assert "Tool Usage Rules" in prompt

    def test_builds_messages(self):
        cb = ContextBuilder(workspace=Path("."))
        history = [{"role": "user", "content": "previous"}, {"role": "assistant", "content": "reply"}]
        msgs = cb.build_messages(
            history=history, current_message="hello",
            channel="feishu", chat_id="oc_test", sender_id="user_1",
        )
        assert len(msgs) == 4  # system + 2 history + 1 user
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[3]["role"] == "user"
        assert "hello" in str(msgs[3]["content"])

    def test_runtime_context_appended(self):
        cb = ContextBuilder(workspace=Path("."))
        msgs = cb.build_messages(
            history=[], current_message="hello",
            channel="feishu", chat_id="oc_test", sender_id="user_1",
        )
        content = str(msgs[1]["content"])
        assert "[Runtime Context" in content
        assert "oc_test" in content
        assert "user_1" in content

    def test_memory_context_injected(self):
        mock_memory = MagicMock()
        mock_memory.get_recent.return_value = [
            {"role": "user", "content": "I like Python", "timestamp": "2026-01-01"},
        ]
        cb = ContextBuilder(workspace=Path("."), memory=mock_memory)
        ctx = cb.get_memory_context("oc_test")
        assert "Python" in ctx

    def test_bootstrap_files_loaded(self, tmp_path):
        (tmp_path / "SOUL.md").write_text("# Soul\nI am helpful.")
        cb = ContextBuilder(workspace=tmp_path)
        prompt = cb.build_system_prompt()
        assert "SOUL.md" in prompt
        assert "I am helpful" in prompt


class TestRequestContext:
    def test_equality(self):
        ctx1 = RequestContext(trace_id="t1", chat_id="c1", chat_type="p2p",
                             user_id="u1", message_id="m1")
        ctx2 = RequestContext(trace_id="t1", chat_id="c1", chat_type="p2p",
                             user_id="u1", message_id="m1")
        assert ctx1 == ctx2

    def test_different_chat_ids(self):
        ctx1 = RequestContext(trace_id="t1", chat_id="c1", chat_type="p2p",
                             user_id="u1", message_id="m1")
        ctx2 = RequestContext(trace_id="t1", chat_id="c2", chat_type="p2p",
                             user_id="u1", message_id="m1")
        assert ctx1 != ctx2

    def test_permissions(self):
        ctx = RequestContext(trace_id="t1", chat_id="c1", chat_type="p2p",
                            user_id="u1", message_id="m1",
                            permissions=frozenset(["web:search", "message:send"]))
        assert "web:search" in ctx.permissions
        assert "admin:delete" not in ctx.permissions
