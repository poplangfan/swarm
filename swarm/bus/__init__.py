"""Message bus — decouples I/O from agent logic."""

from swarm.bus.queue import InboundMessage, MessageBus, OutboundMessage

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
