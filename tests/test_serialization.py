"""Tests for data structures — serialization, immutability, edge cases."""

import json
import pytest
from agent.context import RequestContext
from bus.queue import InboundMessage, OutboundMessage
from agent.runner import AgentRunSpec, AgentRunResult


class TestRequestContextImmutability:
    def test_cannot_modify_chat_id(self):
        ctx = RequestContext(
            trace_id="t1", chat_id="c1", chat_type="p2p",
            user_id="u1", message_id="m1",
        )
        with pytest.raises(Exception):
            ctx.chat_id = "c2"

    def test_hash_works(self):
        ctx = RequestContext(
            trace_id="t1", chat_id="c1", chat_type="p2p",
            user_id="u1", message_id="m1",
        )
        # Frozen dataclass should be hashable
        h = hash(ctx)
        assert isinstance(h, int)

    def test_equality(self):
        ctx1 = RequestContext(
            trace_id="t1", chat_id="c1", chat_type="p2p",
            user_id="u1", message_id="m1",
        )
        ctx2 = RequestContext(
            trace_id="t1", chat_id="c1", chat_type="p2p",
            user_id="u1", message_id="m1",
        )
        assert ctx1 == ctx2

    def test_inequality(self):
        ctx1 = RequestContext(
            trace_id="t1", chat_id="c1", chat_type="p2p",
            user_id="u1", message_id="m1",
        )
        ctx2 = RequestContext(
            trace_id="t2", chat_id="c1", chat_type="p2p",
            user_id="u1", message_id="m1",
        )
        assert ctx1 != ctx2

    def test_permissions_default_empty(self):
        ctx = RequestContext(
            trace_id="t1", chat_id="c1", chat_type="p2p",
            user_id="u1", message_id="m1",
        )
        assert len(ctx.permissions) == 0

    def test_permissions_frozenset(self):
        ctx = RequestContext(
            trace_id="t1", chat_id="c1", chat_type="p2p",
            user_id="u1", message_id="m1",
            permissions=frozenset(["web:search", "message:send"]),
        )
        assert "web:search" in ctx.permissions
        assert "message:send" in ctx.permissions
        assert "admin:delete" not in ctx.permissions


class TestInboundMessage:
    def test_session_key_derivation(self):
        msg = InboundMessage(
            channel="feishu", sender_id="u1",
            chat_id="oc_test_123", content="hello",
        )
        assert msg.session_key == "feishu:oc_test_123"

    def test_session_key_override(self):
        msg = InboundMessage(
            channel="feishu", sender_id="u1",
            chat_id="oc_test_123", content="hello",
            session_key_override="custom:session",
        )
        assert msg.session_key == "custom:session"

    def test_media_defaults_empty(self):
        msg = InboundMessage(
            channel="feishu", sender_id="u1",
            chat_id="c1", content="hello",
        )
        assert msg.media == []

    def test_metadata_defaults_empty(self):
        msg = InboundMessage(
            channel="feishu", sender_id="u1",
            chat_id="c1", content="hello",
        )
        assert msg.metadata == {}


class TestOutboundMessage:
    def test_metadata_default(self):
        msg = OutboundMessage(
            channel="feishu", chat_id="c1", content="hi",
        )
        assert msg.metadata == {}

    def test_custom_metadata(self):
        msg = OutboundMessage(
            channel="feishu", chat_id="c1", content="hi",
            metadata={"trace_id": "trace_123", "stop_reason": "end_turn"},
        )
        assert msg.metadata["trace_id"] == "trace_123"


class TestAgentRunResult:
    def test_defaults(self):
        result = AgentRunResult(
            final_content="Hello",
            stop_reason="end_turn",
        )
        assert result.tools_used == []
        assert result.messages == []
        assert result.had_injections is False
        assert result.usage == {}

    def test_with_tools(self):
        result = AgentRunResult(
            final_content="Done",
            stop_reason="end_turn",
            tools_used=["web_search", "echo"],
            usage={"prompt_tokens": 50, "completion_tokens": 10},
        )
        assert "web_search" in result.tools_used
        assert result.usage["prompt_tokens"] == 50
