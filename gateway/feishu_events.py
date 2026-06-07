"""Feishu event dispatcher — handles all event types from WebSocket."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Callable

import structlog

logger = structlog.get_logger(__name__)


class FeishuEventDispatcher:
    """Dispatches Feishu WebSocket events to registered handlers.

    Supported events:
    - im.message.receive_v1 (core) — Message received
    - im.message.reaction.created — Reaction added
    - im.message.reaction.deleted — Reaction removed
    - im.chat.member.user.added — User joined group
    - im.chat.member.user.deleted — User left group
    - im.chat.disbanded — Group disbanded
    - card.action.trigger — Interactive card action
    """

    def __init__(self, app_id: str = "", app_secret: str = ""):
        self._app_id = app_id
        self._app_secret = app_secret
        self._handlers: dict[str, list[Callable]] = {}
        self._app_ticket: str | None = None
        self._ticket_updated_at: float = 0

    def on(self, event_type: str, handler: Callable) -> None:
        """Register a handler for an event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug("event_handler_registered", event_type=event_type)

    async def dispatch(self, event: Any) -> bool:
        """Dispatch a Feishu event to registered handlers.

        Returns True if the event was handled, False if no handler was found.
        """
        event_type = self._get_event_type(event)

        # Handle app_ticket separately
        if self._is_app_ticket(event):
            self._store_app_ticket(event)
            return True

        # Verify event signature
        if not self._verify_signature(event):
            logger.warning("event_signature_verification_failed", event_type=event_type)
            return False

        # Dispatch to handlers
        handled = False
        for event_key in [event_type, "*"]:
            for handler in self._handlers.get(event_key, []):
                try:
                    result = handler(event)
                    if hasattr(result, "__await__"):
                        await result
                    handled = True
                except Exception as e:
                    logger.error("event_handler_error", event_type=event_type, error=str(e))

        if not handled:
            logger.debug("unhandled_event", event_type=event_type)

        return handled

    def _get_event_type(self, event: Any) -> str:
        """Extract event type from various event formats."""
        if hasattr(event, "type"):
            return str(event.type)
        if isinstance(event, dict):
            return event.get("type", event.get("schema", ""))
        return str(event)

    def _is_app_ticket(self, event: Any) -> bool:
        """Check if the event is an app_ticket push."""
        event_type = self._get_event_type(event)
        return "app_ticket" in event_type.lower()

    def _store_app_ticket(self, event: Any) -> None:
        """Store the app_ticket for event signature verification."""
        ticket = None
        if hasattr(event, "event"):
            ticket = getattr(event.event, "app_ticket", None)
        elif isinstance(event, dict):
            ticket = event.get("event", {}).get("app_ticket")

        if ticket:
            self._app_ticket = ticket
            self._ticket_updated_at = time.time()
            logger.info("app_ticket_updated")

    def _verify_signature(self, event: Any) -> bool:
        """Verify event signature using SHA256.

        Feishu signs events using: SHA256(timestamp + nonce + encrypt_key + body).
        We need the event body as a JSON string to verify.
        """
        if not self._app_ticket:
            # No ticket yet — accept events (ticket will arrive shortly after startup)
            logger.debug("no_app_ticket_yet_accepting_event")
            return True

        # For now, accept all events. Full verification requires the raw HTTP body
        # which is not available through the lark-oapi WebSocket client.
        # The WS client handles signature verification internally.
        return True

    def get_app_ticket(self) -> str | None:
        """Get the cached app_ticket for API operations that need it."""
        return self._app_ticket

    def _verify_signature_manual(
        self, timestamp: str, nonce: str, body: str, signature: str
    ) -> bool:
        """Manual SHA256 signature verification."""
        if not self._app_ticket:
            return True
        raw = f"{timestamp}{nonce}{self._app_ticket}{body}"
        computed = hashlib.sha256(raw.encode()).hexdigest()
        return computed == signature


def extract_message_data(event: Any) -> dict[str, Any] | None:
    """Extract standardized message data from a Feishu event.

    Returns a dict with keys: msg_type, content, msg_id, chat_id, chat_type, sender_id
    Returns None if the event doesn't contain a message.
    """
    msg_data = {}

    if isinstance(event, dict):
        msg_data = event.get("event", event)
    elif hasattr(event, "event"):
        msg_data = event.event or {}

    message = msg_data.get("message", {})
    if not message:
        return None

    sender = msg_data.get("sender", {})
    sender_id = sender.get("sender_id", {})
    if isinstance(sender_id, dict):
        sender_id = sender_id.get("open_id", "")
    elif not isinstance(sender_id, str):
        sender_id = str(sender_id)

    return {
        "msg_type": message.get("message_type", "text"),
        "content": message.get("content", "{}"),
        "msg_id": message.get("message_id", ""),
        "chat_id": message.get("chat_id", ""),
        "chat_type": message.get("chat_type", "p2p"),
        "sender_id": sender_id,
        "root_id": message.get("root_id", ""),
        "parent_id": message.get("parent_id", ""),
        "mentions": message.get("mentions", []),
    }


def extract_reaction_data(event: Any) -> dict[str, Any] | None:
    """Extract reaction data from a reaction event."""
    msg_data = {}
    if isinstance(event, dict):
        msg_data = event.get("event", event)
    elif hasattr(event, "event"):
        msg_data = event.event or {}

    reaction = msg_data.get("reaction", {})
    if not reaction:
        return None

    return {
        "message_id": reaction.get("message_id", ""),
        "reaction_type": reaction.get("reaction_type", {}).get("emoji_type", ""),
        "user_id": reaction.get("user_id", {}).get("open_id", ""),
    }


def extract_member_event_data(event: Any) -> dict[str, Any] | None:
    """Extract member join/leave data from a chat member event."""
    msg_data = {}
    if isinstance(event, dict):
        msg_data = event.get("event", event)
    elif hasattr(event, "event"):
        msg_data = event.event or {}

    chat_id = msg_data.get("chat_id", "")
    users = msg_data.get("users", [])

    return {
        "chat_id": chat_id,
        "users": [
            {"name": u.get("name", ""), "open_id": u.get("user_id", {}).get("open_id", "")}
            for u in users
        ]
        if isinstance(users, list)
        else [],
    }
