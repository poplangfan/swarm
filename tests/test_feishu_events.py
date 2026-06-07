"""Tests for feishu event dispatcher."""

from unittest.mock import MagicMock

import pytest

from gateway.feishu_events import (
    FeishuEventDispatcher,
    extract_member_event_data,
    extract_message_data,
    extract_reaction_data,
)


class TestFeishuEventDispatcher:
    @pytest.mark.asyncio
    async def test_register_and_dispatch(self):
        dispatcher = FeishuEventDispatcher()
        received = []

        async def handler(event):
            received.append(event)

        dispatcher.on("im.message.receive_v1", handler)

        # Create a mock event
        event = MagicMock()
        event.type = "im.message.receive_v1"
        event.event = {
            "message": {
                "message_type": "text",
                "content": '{"text":"hello"}',
                "message_id": "msg_001",
                "chat_id": "oc_test",
                "chat_type": "p2p",
            },
            "sender": {"sender_id": {"open_id": "user_1"}},
        }

        result = await dispatcher.dispatch(event)
        assert result is True
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_multiple_handlers_same_event(self):
        dispatcher = FeishuEventDispatcher()
        r1, r2 = [], []

        async def h1(e):
            r1.append(e)

        async def h2(e):
            r2.append(e)

        dispatcher.on("test_event", h1)
        dispatcher.on("test_event", h2)

        event = MagicMock()
        event.type = "test_event"

        await dispatcher.dispatch(event)
        assert len(r1) == 1
        assert len(r2) == 1

    @pytest.mark.asyncio
    async def test_wildcard_handler(self):
        dispatcher = FeishuEventDispatcher()
        received = []

        async def catch_all(event):
            received.append(event)

        dispatcher.on("*", catch_all)

        event1 = MagicMock()
        event1.type = "event_a"
        event2 = MagicMock()
        event2.type = "event_b"

        await dispatcher.dispatch(event1)
        await dispatcher.dispatch(event2)
        assert len(received) == 2

    def test_app_ticket_storage(self):
        dispatcher = FeishuEventDispatcher()
        event = MagicMock()
        event.type = "app_ticket"
        event.event = MagicMock()
        event.event.app_ticket = "test_ticket_12345"

        import asyncio

        asyncio.run(dispatcher.dispatch(event))
        assert dispatcher.get_app_ticket() == "test_ticket_12345"


class TestExtractFunctions:
    def test_extract_message_data_from_dict(self):
        event = {
            "event": {
                "message": {
                    "message_type": "text",
                    "content": '{"text":"hello"}',
                    "message_id": "msg_001",
                    "chat_id": "oc_123",
                    "chat_type": "p2p",
                },
                "sender": {"sender_id": {"open_id": "user_1"}},
            }
        }
        data = extract_message_data(event)
        assert data is not None
        assert data["msg_type"] == "text"
        assert data["chat_id"] == "oc_123"
        assert data["sender_id"] == "user_1"

    def test_extract_message_data_none(self):
        assert extract_message_data({}) is None

    def test_extract_reaction_data(self):
        event = {
            "event": {
                "reaction": {
                    "message_id": "msg_001",
                    "reaction_type": {"emoji_type": "THUMBSUP"},
                    "user_id": {"open_id": "user_1"},
                }
            }
        }
        data = extract_reaction_data(event)
        assert data is not None
        assert data["reaction_type"] == "THUMBSUP"
        assert data["message_id"] == "msg_001"

    def test_extract_member_event_data(self):
        event = {
            "event": {
                "chat_id": "oc_123",
                "users": [
                    {
                        "name": "Alice",
                        "user_id": {"open_id": "ou_alice"},
                    },
                ],
            }
        }
        data = extract_member_event_data(event)
        assert data is not None
        assert data["chat_id"] == "oc_123"
        assert len(data["users"]) == 1
        assert data["users"][0]["name"] == "Alice"
