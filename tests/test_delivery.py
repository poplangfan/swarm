"""Tests for delivery layer — queuing, rate limiting, retry."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from bus.queue import OutboundMessage
from delivery.delivery import Delivery, DeliveryConfig


class TestDelivery:
    @pytest.mark.asyncio
    async def test_sends_message(self):
        sent = []

        async def mock_send(msg):
            sent.append(msg)
            return "ok"

        delivery = Delivery(
            send_fn=mock_send,
            config=DeliveryConfig(
                max_retries=1,
                base_delay=0.01,
                rate_limit_per_second=1000,
            ),
        )
        msg = OutboundMessage(channel="feishu", chat_id="chat1", content="hello")
        ok = await delivery.send(msg)
        assert ok
        await asyncio.sleep(0.1)  # Let worker process
        assert len(sent) >= 1
        assert "hello" in str(sent[0].content)

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        call_count = 0
        success_after = 2

        async def flaky_send(msg):
            nonlocal call_count
            call_count += 1
            if call_count < success_after:
                raise ConnectionError("temporary error")
            return "ok"

        delivery = Delivery(
            send_fn=flaky_send,
            config=DeliveryConfig(
                max_retries=3,
                base_delay=0.01,
                rate_limit_per_second=1000,
            ),
        )
        msg = OutboundMessage(channel="feishu", chat_id="chat1", content="test")
        await delivery.send(msg)
        await asyncio.sleep(0.3)
        assert call_count >= success_after

    @pytest.mark.asyncio
    async def test_message_ordering_per_chat(self):
        order = []

        async def record_send(msg):
            order.append(msg.content)
            return "ok"

        delivery = Delivery(
            send_fn=record_send,
            config=DeliveryConfig(
                max_retries=1,
                base_delay=0.01,
                rate_limit_per_second=1000,
            ),
        )
        for i in range(5):
            msg = OutboundMessage(channel="feishu", chat_id="chat1", content=f"msg_{i}")
            await delivery.send(msg)
        await delivery.flush()
        assert len(order) == 5
        assert order == [f"msg_{i}" for i in range(5)]

    @pytest.mark.asyncio
    async def test_flush_empty(self):
        delivery = Delivery(send_fn=AsyncMock(return_value="ok"))
        await delivery.flush()  # Should not raise
