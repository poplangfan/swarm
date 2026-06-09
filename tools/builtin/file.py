"""Feishu file tool — list, download, upload files via Drives API."""

from __future__ import annotations

import httpx

from agent.context import RequestContext
from gateway.feishu_token import FeishuTokenManager
from tools.base import ToolBase, tool_result_json


class FeishuFileTool(ToolBase):
    name = "feishu_file"
    description = "List and manage files in Feishu Drives and Docs"
    toolset = "feishu"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "info"],
                "description": "File operation: list recent files, get file info",
            },
            "page_size": {
                "type": "integer",
                "description": "Number of files to list (max 50)",
                "default": 10,
            },
        },
        "required": ["action"],
    }

    @classmethod
    def check_requirements(cls) -> bool:
        return True

    @classmethod
    def required_env_vars(cls) -> list[str]:
        return ["FEISHU_APP_ID", "FEISHU_APP_SECRET"]

    def __init__(
        self,
        app_id: str = "",
        app_secret: str = "",
        domain: str = "feishu",
        token_manager: FeishuTokenManager | None = None,
    ):
        self._app_id = app_id
        self._app_secret = app_secret
        self._domain = domain
        self._token = token_manager or FeishuTokenManager(app_id, app_secret, domain)

    async def execute(self, args: dict, ctx: RequestContext) -> str:
        action = args.get("action", "list")
        if ctx.user_token:
            return await self._user_action(action, args, ctx)
        return await self._app_action(action, args)

    async def _user_action(self, action: str, args: dict, ctx: RequestContext) -> str:
        page_size = min(int(args.get("page_size", 10)), 50)
        if action == "list":
            base = (
                "https://open.feishu.cn"
                if self._domain == "feishu"
                else "https://open.larksuite.com"
            )
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{base}/open-apis/drive/v1/files",
                        headers={"Authorization": f"Bearer {ctx.user_token}"},
                        params={"page_size": page_size},
                        timeout=10.0,
                    )
                    data = resp.json()
                    if data.get("code") != 0:
                        return tool_result_json(error=f"Drive API error: {data.get('msg')}")
                    files = data.get("data", {}).get("files", [])
                    file_list = [
                        {
                            "name": f.get("name", "unknown"),
                            "type": f.get("type", "file"),
                        }
                        for f in files[:page_size]
                    ]
                    return tool_result_json(
                        result=f"Found {len(files)} files",
                        data=file_list,
                    )
            except Exception as e:
                return tool_result_json(error=f"Drive API error: {e}")
        return tool_result_json(error=f"Action '{action}' requires user authorization")

    async def _app_action(self, action: str, args: dict) -> str:
        if action == "list":
            return tool_result_json(
                error="File listing requires user OAuth authorization.",
                result="Please authorize the app to access your files.",
            )
        return tool_result_json(error=f"Action '{action}' not available without user authorization")
