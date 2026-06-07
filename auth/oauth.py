"""Feishu OAuth flow — generate authorization URLs, exchange codes for tokens."""

from __future__ import annotations

import time
from urllib.parse import urlencode

import httpx
import structlog

from auth.token_store import TokenData, TokenStore

logger = structlog.get_logger(__name__)


class FeishuOAuth:
    """Feishu OAuth 2.0 flow for user authorization.

    Flow:
    1. User sends first message → get_authorization_url() returns a link
    2. User clicks link → authorizes in Feishu → redirected to callback
    3. Callback server receives code → exchange_code_for_token()
    4. Token is encrypted and stored → user can now use tools with their identity
    """

    BASE_URLS = {
        "feishu": "https://open.feishu.cn",
        "lark": "https://open.larksuite.com",
    }

    def __init__(self, app_id: str, app_secret: str, redirect_uri: str,
                 token_store: TokenStore, domain: str = "feishu"):
        self._app_id = app_id
        self._app_secret = app_secret
        self._redirect_uri = redirect_uri
        self._token_store = token_store
        self._domain = domain
        self._base = self.BASE_URLS.get(domain, self.BASE_URLS["feishu"])
        self._client = httpx.AsyncClient(
            timeout=10.0,
            headers={"Content-Type": "application/json"},
        )

    def get_authorization_url(self, state: str = "") -> str:
        """Generate the Feishu OAuth authorization URL.

        The user visits this URL in their browser to grant permissions.
        After authorization, Feishu redirects to `redirect_uri` with a `code` parameter.
        """
        params = {
            "app_id": self._app_id,
            "redirect_uri": self._redirect_uri,
        }
        if state:
            params["state"] = state
        return f"{self._base}/open-apis/authen/v1/authorize?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> TokenData | None:
        """Exchange an OAuth authorization code for user_access_token.

        Returns TokenData on success, None on failure.
        """
        try:
            resp = await self._client.post(
                f"{self._base}/open-apis/authen/v1/oidc/access_token",
                json={
                    "grant_type": "authorization_code",
                    "code": code,
                },
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.error("oauth_code_exchange_failed",
                             error=data.get("msg", "unknown"))
                return None

            token_data = data.get("data", {})
            access_token = token_data.get("access_token", "")
            refresh_token = token_data.get("refresh_token", "")
            expires_in = token_data.get("expires_in", 7200)

            return TokenData(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=time.time() + expires_in,
            )
        except Exception as e:
            logger.error("oauth_exchange_error", error=str(e))
            return None

    async def refresh_access_token(self, user_id: str) -> TokenData | None:
        """Refresh an expired user_access_token using the refresh_token."""
        existing = self._token_store.lookup(user_id)
        if not existing:
            return None

        try:
            resp = await self._client.post(
                f"{self._base}/open-apis/authen/v1/oidc/refresh_access_token",
                json={
                    "grant_type": "refresh_token",
                    "refresh_token": existing.refresh_token,
                },
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.error("token_refresh_failed", user_id=user_id,
                             error=data.get("msg", "unknown"))
                return None

            token_data = data.get("data", {})
            new_token = TokenData(
                access_token=token_data.get("access_token", ""),
                refresh_token=token_data.get("refresh_token", existing.refresh_token),
                expires_at=time.time() + token_data.get("expires_in", 7200),
            )
            self._token_store.save(user_id, new_token)
            logger.info("token_refreshed", user_id=user_id)
            return new_token
        except Exception as e:
            logger.error("token_refresh_error", user_id=user_id, error=str(e))
            return None

    async def get_or_refresh_token(self, user_id: str) -> str | None:
        """Get a valid user_access_token, refreshing if expired.

        Returns the access_token string, or None if user hasn't authorized.
        """
        token = self._token_store.lookup(user_id)
        if not token:
            return None

        if token.is_expired():
            refreshed = await self.refresh_access_token(user_id)
            if refreshed:
                return refreshed.access_token
            return None

        return token.access_token
