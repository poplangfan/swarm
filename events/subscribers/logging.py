"""Logging subscriber — routes all events to structured logs."""

from __future__ import annotations

import structlog

from events.bus import Event

logger = structlog.get_logger(__name__)


async def log_event(event: Event) -> None:
    """Log an event as a structured log entry."""
    log_data = {
        "event_type": event.type.value,
        "trace_id": event.trace_id,
        "chat_id": event.chat_id,
        "user_id": event.user_id,
        **event.data,
    }
    logger.info("runtime_event", **log_data)
