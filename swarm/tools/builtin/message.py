"""Feishu message tool — send messages, add reactions via bot API."""

from __future__ import annotations

import json

import httpx
import structlog

from swarm.agent.context import RequestContext
from swarm.gateway.feishu_token import FeishuTokenManager
from swarm.tools.base import ToolBase, tool_result

logger = structlog.get_logger(__name__)


class FeishuMessageTool(ToolBase):
    """Send messages and manage reactions in Feishu conversations."""

    name = "feishu_message"
    description = "Send messages or add reactions in a Feishu conversation"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["send_text", "add_reaction", "send_markdown"],
                "description": "The action to perform",
            },
            "content": {
                "type": "string",
                "description": "Message content (text or markdown depending on action)",
            },
            "emoji": {
                "type": "string",
                "description": "Emoji type for add_reaction (e.g. THUMBSUP, HEART, OK)",
            },
        },
        "required": ["action"],
    }

    def __init__(self, app_id: str = "", app_secret: str = "", domain: str = "feishu",
                 token_manager: FeishuTokenManager | None = None):
        self._app_id = app_id
        self._app_secret = app_secret
        self._domain = domain
        self._token = token_manager or FeishuTokenManager(app_id, app_secret, domain)

    async def execute(self, args: dict, ctx: RequestContext) -> str:
        action = args.get("action", "send_text")
        try:
            if action == "send_text":
                return await self._send_text(ctx.chat_id, args.get("content", ""))
            elif action == "send_markdown":
                return await self._send_text(ctx.chat_id, args.get("content", ""),
                                            msg_type="interactive")
            elif action == "add_reaction":
                return await self._add_reaction(ctx.chat_id, ctx.message_id,
                                                args.get("emoji", "THUMBSUP"))
            return tool_result(f"Unknown action: {action}")
        except Exception as e:
            return tool_result(f"Feishu API error: {e}")

    async def _send_text(self, chat_id: str, content: str,
                         msg_type: str = "text") -> str:
        token = await self._token.get_token()
        base = "https://open.feishu.cn" if self._domain == "feishu" else "https://open.larksuite.com"

        if msg_type == "interactive":
            card = {
                "config": {"wide_screen_mode": True},
                "elements": [{"tag": "markdown", "content": content}],
            }
            body = {"msg_type": "interactive", "content": json.dumps(card)}
        else:
            body = {"msg_type": "text", "content": json.dumps({"text": content})}

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base}/open-apis/im/v1/messages/{chat_id}/reply",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body, timeout=10.0,
            )
            data = resp.json()
            if data.get("code") == 0:
                return tool_result("Message sent", message_id=data.get("data", {}).get("message_id", ""))
            return tool_result(f"Send failed: {data.get('msg')}")

    async def _add_reaction(self, chat_id: str, message_id: str, emoji: str) -> str:
        token = await self._token.get_token()
        base = "https://open.feishu.cn" if self._domain == "feishu" else "https://open.larksuite.com"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base}/open-apis/im/v1/messages/{message_id}/reactions",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"reaction_type": {"emoji_type": emoji}}, timeout=10.0,
            )
            data = resp.json()
            if data.get("code") == 0:
                return tool_result(f"Reaction {emoji} added")
            return tool_result(f"Reaction failed: {data.get('msg')}")
