"""Feishu outbound message builder — text, card, reactions, and streaming."""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

from gateway.feishu_token import FeishuTokenManager

logger = structlog.get_logger(__name__)


class FeishuReply:
    """Build and send Feishu message replies in multiple formats.

    Supported formats:
    - text: Plain text message
    - interactive: Card-based message with markdown
    - share_chat: Share a chat to another conversation
    - reaction: Add emoji reaction to a message
    """

    def __init__(self, app_id: str, app_secret: str, domain: str = "feishu"):
        self._app_id = app_id
        self._app_secret = app_secret
        self._domain = domain
        self._base = (
            "https://open.feishu.cn" if domain == "feishu" else "https://open.larksuite.com"
        )
        self._token = FeishuTokenManager(app_id, app_secret, domain)

    async def _post(self, path: str, body: dict) -> dict:
        """Make an authenticated POST request to Feishu API."""
        token = await self._token.get_token()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base}{path}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body,
                timeout=10.0,
            )
            return resp.json()

    async def _patch(self, path: str, body: dict) -> dict:
        """Make an authenticated PATCH request to Feishu API."""
        token = await self._token.get_token()
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{self._base}{path}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body,
                timeout=10.0,
            )
            return resp.json()

    # ── Message Sending ─────────────────────────────────────

    async def send_text(
        self, chat_id: str, content: str, reply_to: str | None = None
    ) -> str | None:
        """Send a plain text message.

        If reply_to is provided, sends as a reply to that message.
        Otherwise, sends as a new message to the chat.
        """
        body: dict[str, Any] = {
            "msg_type": "text",
            "content": json.dumps({"text": content}),
        }

        if reply_to:
            # Reply to a specific message in thread
            path = f"/open-apis/im/v1/messages/{reply_to}/reply"
        else:
            # Send as new message to chat
            path = f"/open-apis/im/v1/messages?receive_id_type=chat_id"
            body["receive_id"] = chat_id

        data = await self._post(path, body)
        if data.get("code") != 0:
            logger.error("send_text_failed", error=data.get("msg"), chat_id=chat_id)
            return None
        return data.get("data", {}).get("message_id")

    async def send_markdown_card(
        self, chat_id: str, content: str, title: str = "Swarm", color: str = "blue"
    ) -> str | None:
        """Send a message as an interactive card with markdown content.

        Colors: blue, wathet, turquoise, green, yellow, orange, red, purple
        """
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color,
            },
            "elements": [{"tag": "markdown", "content": content}],
        }
        body = {
            "msg_type": "interactive",
            "content": json.dumps(card),
        }
        data = await self._post(f"/open-apis/im/v1/messages/{chat_id}/reply", body)
        if data.get("code") != 0:
            logger.error("send_card_failed", error=data.get("msg"))
            return None
        return data.get("data", {}).get("message_id")

    async def send_card_with_actions(
        self,
        chat_id: str,
        content: str,
        title: str = "Swarm",
        actions: list[dict] | None = None,
        color: str = "blue",
    ) -> str | None:
        """Send a card with interactive action buttons.

        Actions format:
        [
            {"tag": "button", "text": {"tag": "plain_text", "content": "Approve"},
             "type": "primary", "value": {"action": "approve"}},
            {"tag": "button", "text": {"tag": "plain_text", "content": "Reject"},
             "type": "danger", "value": {"action": "reject"}},
        ]
        """
        elements = [{"tag": "markdown", "content": content}]
        if actions:
            elements.append(
                {
                    "tag": "action",
                    "actions": actions,
                }
            )

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color,
            },
            "elements": elements,
        }
        body = {"msg_type": "interactive", "content": json.dumps(card)}
        data = await self._post(f"/open-apis/im/v1/messages/{chat_id}/reply", body)
        if data.get("code") != 0:
            logger.error("send_action_card_failed", error=data.get("msg"))
            return None
        return data.get("data", {}).get("message_id")

    async def send_error_card(self, chat_id: str, error_msg: str) -> str | None:
        """Send an error notification card (red header)."""
        return await self.send_markdown_card(
            chat_id=chat_id,
            content=f"❌ {error_msg}",
            title="Error",
            color="red",
        )

    async def send_success_card(
        self, chat_id: str, content: str, title: str = "Complete"
    ) -> str | None:
        """Send a success notification card (green header)."""
        return await self.send_markdown_card(
            chat_id=chat_id,
            content=f"✅ {content}",
            title=title,
            color="green",
        )

    async def send_thinking_card(self, chat_id: str) -> str | None:
        """Send an initial 'thinking' card before streaming response."""
        return await self.send_markdown_card(
            chat_id=chat_id,
            content="thinking...",
            title="Swarm",
            color="blue",
        )

    # ── Message Update ──────────────────────────────────────

    async def update_card(
        self, message_id: str, content: str, title: str = "Swarm", color: str = "blue"
    ) -> bool:
        """Update an existing interactive card message."""
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color,
            },
            "elements": [{"tag": "markdown", "content": content}],
        }
        body = {"content": json.dumps(card)}
        data = await self._patch(f"/open-apis/im/v1/messages/{message_id}", body)
        if data.get("code") != 0:
            logger.error("update_card_failed", error=data.get("msg"), message_id=message_id)
            return False
        return True

    # ── Reactions ────────────────────────────────────────────

    async def add_reaction(self, message_id: str, emoji_type: str) -> bool:
        """Add an emoji reaction to a message.

        Common emoji types: THUMBSUP, HEART, OK, LAUGH, CRY, CLAP, FIST, WAVE, HUG, FLEX
        Custom emoji: use the emoji key (emoji_xxx)
        """
        body = {"reaction_type": {"emoji_type": emoji_type}}
        data = await self._post(f"/open-apis/im/v1/messages/{message_id}/reactions", body)
        if data.get("code") != 0:
            logger.debug("reaction_failed", error=data.get("msg"), emoji=emoji_type)
            return False
        return True

    async def remove_reaction(self, message_id: str, emoji_type: str) -> bool:
        """Remove an emoji reaction from a message."""
        data = await self._post(
            f"/open-apis/im/v1/messages/{message_id}/reactions/{emoji_type}/remove",
            {},
        )
        return data.get("code") == 0

    async def mark_processing(self, chat_id: str, message_id: str) -> None:
        """Show processing state on the original message."""
        # Feishu doesn't have a built-in "processing" indicator per-message.
        # Instead, we add a reaction to acknowledge receipt.
        await self.add_reaction(message_id, "THUMBSUP")

    async def mark_done(self, message_id: str) -> None:
        """Mark processing as complete (remove THUMBSUP, add OK)."""
        await self.add_reaction(message_id, "OK")

    async def mark_error(self, message_id: str) -> None:
        """Mark processing as failed."""
        await self.add_reaction(message_id, "CROSS_MARK")

    # ── Message Content Helpers ──────────────────────────────

    @staticmethod
    def build_mention(open_id: str, name: str = "") -> str:
        """Build an @mention string for Feishu messages."""
        return f'<at user_id="{open_id}">{name or open_id}</at>'

    @staticmethod
    def build_mention_all() -> str:
        """Build an @everyone mention."""
        return '<at user_id="all">everyone</at>'

    @staticmethod
    def build_link(url: str, text: str = "") -> str:
        """Build a hyperlink for Feishu messages."""
        display = text or url
        return f"[{display}]({url})"

    @staticmethod
    def build_code_block(code: str, language: str = "") -> str:
        """Build a code block for Feishu markdown."""
        return f"```{language}\n{code}\n```"

    @staticmethod
    def build_progress_bar(percent: float, width: int = 10) -> str:
        """Build a text-based progress bar."""
        filled = int(width * percent / 100)
        bar = "█" * filled + "░" * (width - filled)
        return f"`[{bar}] {percent:.0f}%`"

    # ── Message Queries ─────────────────────────────────────

    async def get_message(self, message_id: str) -> dict | None:
        """Fetch a message by ID."""
        token = await self._token.get_token()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base}/open-apis/im/v1/messages/{message_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            data = resp.json()
            if data.get("code") != 0:
                return None
            return data.get("data", {})

    async def get_thread_messages(self, thread_id: str, page_size: int = 20) -> list[dict]:
        """Fetch messages in a thread."""
        token = await self._token.get_token()
        items = []
        page_token = ""
        while True:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._base}/open-apis/im/v1/messages/{thread_id}/thread",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"page_size": min(page_size, 50), "page_token": page_token},
                    timeout=10.0,
                )
                data = resp.json()
                if data.get("code") != 0:
                    break
                batch = data.get("data", {}).get("items", [])
                items.extend(batch)
                if not data.get("data", {}).get("has_more"):
                    break
                page_token = data.get("data", {}).get("page_token", "")
        return items
