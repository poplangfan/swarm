"""Message bus — decouples I/O from agent logic."""

from bus.queue import InboundMessage, MessageBus, OutboundMessage

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
