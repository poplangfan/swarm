"""Shared Feishu tenant access token manager.

Single token cache shared across FeishuReply, CardKitStreamer, and
any other Feishu API client — avoids redundant token requests.
"""

from __future__ import annotations

import time

import httpx
import structlog

logger = structlog.get_logger(__name__)


class FeishuTokenManager:
    """Cached tenant access token for Feishu Open API calls.

    Refreshes automatically when the token is within 60 seconds of expiry.
    Share one instance across all Feishu API clients.
    """

    def __init__(self, app_id: str, app_secret: str, domain: str = "feishu"):
        self._app_id = app_id
        self._app_secret = app_secret
        self._base = (
            "https://open.feishu.cn"
            if domain == "feishu"
            else "https://open.larksuite.com"
        )
        self._token: str | None = None
        self._expires: float = 0

    async def get_token(self) -> str:
        """Get a valid tenant access token, refreshing if needed."""
        if self._token and time.time() < self._expires - 60:
            return self._token

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self._base}/open-apis/auth/v3/tenant_access_token/internal",
                    json={"app_id": self._app_id, "app_secret": self._app_secret},
                    timeout=10.0,
                )
                data = resp.json()
                if data.get("code") != 0:
                    raise RuntimeError(f"Token error: {data.get('msg')}")
                self._token = data["tenant_access_token"]
                self._expires = time.time() + data.get("expire", 7200)
                return self._token
        except Exception as e:
            logger.error("token_fetch_failed", error=str(e))
            raise
