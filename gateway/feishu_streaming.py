"""CardKit streaming engine — real-time message card updates for Feishu."""

from __future__ import annotations

import json
import time

import httpx
import structlog

from gateway.feishu_token import FeishuTokenManager

logger = structlog.get_logger(__name__)


class CardKitStreamer:
    """Manages Feishu CardKit streaming: create card, stream deltas, finalize.

    Feishu's CardKit API allows progressive message updates:
    1. Send initial card with a streaming element
    2. Send incremental updates (deltas) as content arrives
    3. Finalize the card into its final rendered state

    Rate-limited to `edit_interval` seconds between updates to avoid API throttling.
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        domain: str = "feishu",
        edit_interval: float = 0.5,
    ):
        self._app_id = app_id
        self._app_secret = app_secret
        self._domain = domain
        self._edit_interval = edit_interval
        self._token = FeishuTokenManager(app_id, app_secret, domain)

        # Per-chat stream buffers
        self._buffers: dict[str, _StreamBuffer] = {}

    async def start_stream(self, chat_id: str) -> str | None:
        """Create an initial streaming message card. Returns the message_id."""
        token = await self._token.get_token()
        base = (
            "https://open.feishu.cn" if self._domain == "feishu" else "https://open.larksuite.com"
        )

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "Swarm"},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": "thinking...",
                    "element_id": "streaming_md",
                }
            ],
        }

        body = {
            "msg_type": "interactive",
            "content": json.dumps(card),
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base}/open-apis/im/v1/messages/{chat_id}/reply",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=10.0,
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.error("stream_start_failed", error=data.get("msg"))
                return None
            msg_id = data.get("data", {}).get("message_id")
            self._buffers[chat_id] = _StreamBuffer(msg_id=msg_id or "")
            return msg_id

    async def send_delta(self, chat_id: str, content: str) -> bool:
        """Send a streaming delta to update the card."""
        buf = self._buffers.get(chat_id)
        if not buf:
            return False

        buf.text += content
        now = time.time()
        if now - buf.last_edit < self._edit_interval:
            return True  # Throttled — content is buffered

        return await self._flush_delta(chat_id, buf)

    async def finalize(self, chat_id: str) -> str:
        """Finalize the streaming card and return the accumulated text."""
        buf = self._buffers.get(chat_id)
        if not buf:
            return ""

        # Flush any remaining content
        await self._flush_delta(chat_id, buf, force=True)

        # Update card with final content (no streaming element)
        token = await self._token.get_token()
        base = (
            "https://open.feishu.cn" if self._domain == "feishu" else "https://open.larksuite.com"
        )

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "Swarm"},
                "template": "green",
            },
            "elements": [{"tag": "markdown", "content": buf.text}],
        }

        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{base}/open-apis/im/v1/messages/{buf.msg_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"content": json.dumps(card)},
                timeout=10.0,
            )

        text = buf.text
        del self._buffers[chat_id]
        return text

    async def _flush_delta(self, chat_id: str, buf: _StreamBuffer, force: bool = False) -> bool:
        """Send the buffered text as a card update."""
        if not force and time.time() - buf.last_edit < self._edit_interval:
            return True

        token = await self._token.get_token()
        base = (
            "https://open.feishu.cn" if self._domain == "feishu" else "https://open.larksuite.com"
        )

        card = {
            "config": {"wide_screen_mode": True},
            "elements": [
                {"tag": "markdown", "content": buf.text + " ▌", "element_id": "streaming_md"}
            ],
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.patch(
                    f"{base}/open-apis/im/v1/messages/{buf.msg_id}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json={"content": json.dumps(card)},
                    timeout=5.0,
                )
                data = resp.json()
                if data.get("code") != 0:
                    logger.warning("delta_send_failed", error=data.get("msg"))
                    return False
        except Exception as e:
            logger.warning("delta_exception", error=str(e))
            return False

        buf.last_edit = time.time()
        return True


class _StreamBuffer:
    """Per-chat streaming state."""

    def __init__(self, msg_id: str):
        self.msg_id = msg_id
        self.text: str = ""
        self.last_edit: float = 0.0
