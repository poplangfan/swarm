"""Tests for events system."""

import pytest

from events.bus import Event, EventBus, EventType


class TestEventBus:
    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self):
        bus = EventBus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(EventType.TURN_COMPLETED, handler)
        await bus.turn_completed("trace1", "chat1", latency_ms=100)

        assert len(received) == 1
        assert received[0].type == EventType.TURN_COMPLETED
        assert received[0].data["latency_ms"] == 100

    @pytest.mark.asyncio
    async def test_wildcard_subscriber(self):
        bus = EventBus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe("*", handler)
        await bus.turn_started("t1", "c1")
        await bus.tool_executed("search", 50.0)

        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        bus = EventBus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(EventType.ERROR_OCCURRED, handler)
        await bus.error_occurred("test error")
        assert len(received) == 1

        bus.unsubscribe(EventType.ERROR_OCCURRED, handler)
        await bus.error_occurred("another error")
        assert len(received) == 1  # Still 1 — second not received

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        bus = EventBus()
        r1, r2 = [], []

        async def h1(e):
            r1.append(e)

        async def h2(e):
            r2.append(e)

        bus.subscribe(EventType.SESSION_CREATED, h1)
        bus.subscribe(EventType.SESSION_CREATED, h2)
        await bus.session_created("chat1")

        assert len(r1) == 1
        assert len(r2) == 1


class TestEventCreation:
    def test_event_defaults(self):
        event = Event(type=EventType.TURN_STARTED)
        assert event.type == EventType.TURN_STARTED
        assert event.timestamp > 0
        assert event.trace_id is None

    def test_event_with_data(self):
        event = Event(
            type=EventType.TOOL_EXECUTED,
            trace_id="t1",
            data={"tool_name": "search", "duration_ms": 50.0},
        )
        assert event.data["tool_name"] == "search"
        assert event.trace_id == "t1"
