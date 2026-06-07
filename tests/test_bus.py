"""Tests for message bus."""

import pytest
from bus.queue import MessageBus, InboundMessage, OutboundMessage


def make_msg(chat_id: str, content: str = "hello") -> InboundMessage:
    return InboundMessage(channel="feishu", sender_id="user_1",
                          chat_id=chat_id, content=content)


class TestMessageBus:
    @pytest.mark.asyncio
    async def test_publish_and_consume(self):
        bus = MessageBus()
        await bus.publish_inbound(make_msg("chat_A"))
        consumed = await bus.consume_inbound()
        assert consumed.chat_id == "chat_A"
        assert consumed.content == "hello"

    @pytest.mark.asyncio
    async def test_fifo_ordering(self):
        bus = MessageBus()
        await bus.publish_inbound(make_msg("A", "first"))
        await bus.publish_inbound(make_msg("B", "second"))
        await bus.publish_inbound(make_msg("C", "third"))
        m1 = await bus.consume_inbound()
        m2 = await bus.consume_inbound()
        m3 = await bus.consume_inbound()
        assert m1.content == "first"
        assert m2.content == "second"
        assert m3.content == "third"

    @pytest.mark.asyncio
    async def test_stop_accepting(self):
        bus = MessageBus()
        bus.stop_accepting()
        await bus.publish_inbound(make_msg("A"))

    def test_session_key_derivation(self):
        msg = InboundMessage(channel="feishu", sender_id="u1", chat_id="oc_123", content="hi")
        assert msg.session_key == "feishu:oc_123"

    def test_session_key_override(self):
        msg = InboundMessage(channel="feishu", sender_id="u1", chat_id="oc_123",
                             content="hi", session_key_override="custom:key")
        assert msg.session_key == "custom:key"
