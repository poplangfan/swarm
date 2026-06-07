"""Feishu interactive card actions — handle button clicks and form submissions.

When users interact with Swarm's message cards (click buttons, submit forms),
Feishu sends a card.action.trigger event. This module handles those callbacks
and routes them back into the AgentLoop as synthetic messages.
"""

from __future__ import annotations

import json
import time
from typing import Any

import structlog

from bus.queue import InboundMessage, MessageBus

logger = structlog.get_logger(__name__)


class CardActionHandler:
    """Handles interactive card action callbacks from Feishu.

    Card actions (button clicks, form submissions) are converted into
    synthetic InboundMessages and published to the MessageBus, allowing
    the AgentLoop to process them like regular messages.
    """

    def __init__(self, bus: MessageBus):
        self._bus = bus
        self._handlers: dict[str, dict[str, ActionHandler]] = {}

    def register(
        self, action_id: str, handler: callable,
        label: str = "", description: str = "",
    ) -> None:
        """Register a handler for a specific card action.

        Args:
            action_id: Unique identifier for the action (referenced in card JSON)
            handler: Async callable that receives (action_data, chat_id, user_id)
            label: Human-readable label for the action
            description: What the action does
        """
        self._handlers[action_id] = {
            "handler": handler,
            "label": label,
            "description": description,
        }
        logger.debug("card_action_registered", action_id=action_id, label=label)

    async def handle_event(self, event: Any) -> bool:
        """Process a card.action.trigger event.

        Returns True if the action was handled.
        """
        action_data = self._extract_action_data(event)
        if not action_data:
            return False

        action_id = action_data.get("action_id", "")
        if not action_id:
            return False

        handler_info = self._handlers.get(action_id)
        if not handler_info:
            logger.warning("unhandled_card_action", action_id=action_id)
            return False

        handler = handler_info["handler"]
        chat_id = action_data.get("chat_id", "")
        user_id = action_data.get("user_id", "")
        action_value = action_data.get("action_value", {})

        try:
            result = handler(action_value, chat_id, user_id)
            if hasattr(result, '__await__'):
                await result
            logger.info("card_action_handled", action_id=action_id,
                        chat_id=chat_id, user_id=user_id)
            return True
        except Exception as e:
            logger.error("card_action_error", action_id=action_id, error=str(e))
            return False

    def _extract_action_data(self, event: Any) -> dict[str, Any] | None:
        """Extract action data from a card.action.trigger event."""
        msg_data = {}
        if hasattr(event, 'event'):
            msg_data = event.event or {}
        elif isinstance(event, dict):
            msg_data = event

        action = msg_data.get('action', {})
        if not action:
            return None

        return {
            "action_id": action.get("action_id", ""),
            "action_value": action.get("value", action.get("option", {})),
            "chat_id": msg_data.get("open_chat_id", msg_data.get("chat_id", "")),
            "user_id": msg_data.get("operator", {}).get("open_id", ""),
            "message_id": msg_data.get("open_message_id", ""),
        }

    async def route_as_message(self, action_id: str, action_data: dict,
                               chat_id: str, user_id: str) -> None:
        """Route a card action as a synthetic inbound message.

        This allows card interactions to trigger AgentLoop processing
        as if the user had sent a regular message.
        """
        synthetic_content = (
            f"[Card Action: {action_id}]\n"
            f"Data: {json.dumps(action_data, ensure_ascii=False)}"
        )

        msg = InboundMessage(
            channel="feishu",
            sender_id=user_id,
            chat_id=chat_id,
            content=synthetic_content,
            metadata={
                "message_id": f"card_action_{action_id}_{int(time.time() * 1000)}",
                "chat_type": "p2p",
                "msg_type": "card_action",
                "card_action_id": action_id,
            },
        )
        await self._bus.publish_inbound(msg)
        logger.debug("card_action_routed_as_message", action_id=action_id)


# Type alias for action handler functions
ActionHandler = callable
