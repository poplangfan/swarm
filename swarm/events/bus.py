"""Publish/subscribe event bus — decouples event producers from consumers."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

import structlog

logger = structlog.get_logger(__name__)


class EventType(Enum):
    """Standard Swarm runtime events."""
    SESSION_CREATED = "session_created"
    SESSION_EXPIRED = "session_expired"
    TURN_STARTED = "turn_started"
    TURN_COMPLETED = "turn_completed"
    TOOL_EXECUTED = "tool_executed"
    SUBAGENT_SPAWNED = "subagent_spawned"
    SUBAGENT_COMPLETED = "subagent_completed"
    TOKEN_REFRESHED = "token_refreshed"
    MEMORY_CONSOLIDATED = "memory_consolidated"
    ERROR_OCCURRED = "error_occurred"
    HEALTH_CHANGED = "health_changed"


@dataclass
class Event:
    """A single runtime event."""
    type: EventType
    timestamp: float = field(default_factory=time.time)
    trace_id: str | None = None
    chat_id: str | None = None
    user_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


# Type alias for subscriber callbacks
Subscriber = Callable[[Event], Any]


class EventBus:
    """Simple publish/subscribe event bus with async subscriber support.

    Subscribers register for specific event types or "*" (all events).
    Events are dispatched synchronously to all matching subscribers.
    Long-running subscribers should spawn their own tasks.
    """

    def __init__(self):
        self._subscribers: dict[str, list[Subscriber]] = {}

    def subscribe(self, event_type: EventType | str, callback: Subscriber) -> None:
        """Register a callback for an event type."""
        key = event_type.value if isinstance(event_type, EventType) else event_type
        if key not in self._subscribers:
            self._subscribers[key] = []
        self._subscribers[key].append(callback)

    def unsubscribe(self, event_type: EventType | str, callback: Subscriber) -> None:
        """Remove a subscriber callback."""
        key = event_type.value if isinstance(event_type, EventType) else event_type
        if key in self._subscribers:
            try:
                self._subscribers[key].remove(callback)
            except ValueError:
                pass

    async def publish(self, event: Event) -> None:
        """Publish an event to all matching subscribers concurrently."""
        keys = [event.type.value, "*"]
        coros = []
        for key in keys:
            for sub in self._subscribers.get(key, []):
                coros.append(self._invoke_subscriber(sub, event))
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    async def _invoke_subscriber(self, sub: Subscriber, event: Event) -> None:
        """Invoke a single subscriber, handling sync and async callbacks."""
        try:
            result = sub(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            logger.exception("event_subscriber_error",
                             event_type=event.type.value,
                             subscriber=str(sub))

    # ── Convenience methods ──────────────────────────────────

    async def session_created(self, chat_id: str, **kwargs) -> None:
        await self.publish(Event(type=EventType.SESSION_CREATED, chat_id=chat_id,
                                 data=kwargs))

    async def turn_started(self, trace_id: str, chat_id: str, **kwargs) -> None:
        await self.publish(Event(type=EventType.TURN_STARTED, trace_id=trace_id,
                                 chat_id=chat_id, data=kwargs))

    async def turn_completed(self, trace_id: str, chat_id: str,
                             latency_ms: int = 0, **kwargs) -> None:
        await self.publish(Event(
            type=EventType.TURN_COMPLETED, trace_id=trace_id,
            chat_id=chat_id,
            data={"latency_ms": latency_ms, **kwargs},
        ))

    async def tool_executed(self, name: str, duration_ms: float,
                            trace_id: str | None = None, **kwargs) -> None:
        await self.publish(Event(
            type=EventType.TOOL_EXECUTED, trace_id=trace_id,
            data={"tool_name": name, "duration_ms": duration_ms, **kwargs},
        ))

    async def error_occurred(self, error: str, trace_id: str | None = None,
                             chat_id: str | None = None, **kwargs) -> None:
        await self.publish(Event(
            type=EventType.ERROR_OCCURRED, trace_id=trace_id,
            chat_id=chat_id,
            data={"error": error, **kwargs},
        ))
