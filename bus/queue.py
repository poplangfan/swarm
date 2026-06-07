"""Async message bus — decouples I/O channels from the agent core."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class InboundMessage:
    """A message received from an external channel."""
    channel: str
    sender_id: str
    chat_id: str
    content: str
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    session_key_override: str | None = None

    @property
    def session_key(self) -> str:
        return self.session_key_override or f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    """A message to be sent to an external channel."""
    channel: str
    chat_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class MessageBus:
    """Async message bus using asyncio.Queue."""

    def __init__(self, maxsize: int = 1024):
        self._inbound: asyncio.Queue[InboundMessage] = asyncio.Queue(maxsize=maxsize)
        self._outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue(maxsize=maxsize)
        self._accepting: bool = True

    async def publish_inbound(self, msg: InboundMessage) -> bool:
        """Publish an inbound message. Returns False if queue is full (message dropped)."""
        if not self._accepting:
            return False
        try:
            self._inbound.put_nowait(msg)
            return True
        except asyncio.QueueFull:
            logger.warning("inbound_queue_full",
                           chat_id=msg.chat_id,
                           content_preview=str(msg.content)[:100])
            return False

    async def consume_inbound(self) -> InboundMessage:
        return await self._inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        try:
            self._outbound.put_nowait(msg)
        except asyncio.QueueFull:
            logger.warning("outbound_queue_full",
                          chat_id=msg.chat_id,
                          content_preview=str(msg.content)[:100])

    async def consume_outbound(self) -> OutboundMessage:
        return await self._outbound.get()

    def stop_accepting(self) -> None:
        self._accepting = False

    @property
    def inbound_size(self) -> int:
        return self._inbound.qsize()

    @property
    def outbound_size(self) -> int:
        return self._outbound.qsize()
