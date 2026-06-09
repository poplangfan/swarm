"""Feishu authorization tool — trigger OAuth flow from chat.

Allows users to authorize the bot to access their Feishu resources
(wiki/docs/bitable/sheets) with a simple /auth command or LLM-initiated action.
"""

from __future__ import annotations

import os
from urllib.parse import urlencode

from agent.context import RequestContext
from tools.base import ToolBase, tool_result_json


class FeishuAuthTool(ToolBase):
    """Generate Feishu OAuth authorization URLs and check auth status."""

    name = "feishu_auth"
    description = (
        "Check Feishu authorization status or generate an authorization URL "
        "for accessing Feishu documents, wikis, and bitables"
    )
    toolset = "feishu"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "authorize"],
                "description": "Check status or generate authorization URL",
            },
        },
        "required": ["action"],
    }

    @classmethod
    def check_requirements(cls) -> bool:
        return bool(os.environ.get("FEISHU_APP_ID"))

    @classmethod
    def required_env_vars(cls) -> list[str]:
        return ["FEISHU_APP_ID", "FEISHU_APP_SECRET"]

    async def execute(self, args: dict, ctx: RequestContext) -> str:
        action = args.get("action", "status")

        if action == "status":
            if ctx.user_token:
                return tool_result_json(
                    result="Feishu authorization is active",
                    data={"authorized": True},
                )
            return tool_result_json(
                result="Not authorized. Use the 'authorize' action to get a link.",
                data={"authorized": False},
            )

        elif action == "authorize":
            app_id = os.environ.get("FEISHU_APP_ID", "")
            domain = os.environ.get("FEISHU_DOMAIN", "feishu")
            base = "https://open.feishu.cn" if domain == "feishu" else "https://open.larksuite.com"

            if not app_id:
                return tool_result_json(
                    error="Feishu app not configured",
                    result="FEISHU_APP_ID environment variable is not set.",
                )

            params = {
                "app_id": app_id,
                "redirect_uri": "http://localhost:9876/oauth/callback",
                "state": ctx.user_id,
            }
            auth_url = f"{base}/open-apis/authen/v1/authorize?{urlencode(params)}"

            return tool_result_json(
                result="Authorization link generated",
                data={
                    "auth_url": auth_url,
                    "instructions": (
                        "Click the link to authorize Swarm to access your Feishu "
                        "documents, wikis, bitables, and sheets. After authorization, "
                        "you can use commands to read and search Feishu content."
                    ),
                    "expires_in": "Authorization code expires in 10 minutes",
                },
            )

        return tool_result_json(error=f"Unknown action: {action}")
