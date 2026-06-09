"""Web fetch tool — fetch URL content and convert to markdown text."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from agent.context import RequestContext
from tools.base import ToolBase, tool_result_json

_FEISHU_AUTH_DOMAINS = {
    "horizonrobotics.feishu.cn",
    "feishu.cn",
    "larksuite.com",
}
_FEISHU_DOC_PREFIXES = ("/wiki/", "/docs/", "/base/", "/sheet/", "/mindnotes/")


class WebFetchTool(ToolBase):
    name = "web_fetch"
    description = "Fetch content from a URL and extract the readable text"
    toolset = "web"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to fetch"},
            "max_chars": {
                "type": "integer",
                "description": "Max characters to return",
                "default": 8000,
            },
        },
        "required": ["url"],
    }

    _shared_client: httpx.AsyncClient | None = None

    @classmethod
    def _get_client(cls) -> httpx.AsyncClient:
        if cls._shared_client is None:
            cls._shared_client = httpx.AsyncClient(
                timeout=15.0,
                follow_redirects=True,
                headers={"User-Agent": "Swarm/1.0 (compatible; bot)"},
            )
        return cls._shared_client

    async def execute(self, args: dict, ctx: RequestContext) -> str:
        url = args.get("url", "")
        max_chars = min(int(args.get("max_chars", 8000)), 32000)

        if not url.startswith(("http://", "https://")):
            return tool_result_json(error=f"Invalid URL: {url}")

        if self._is_feishu_doc_url(url):
            if not ctx.user_token:
                # Build auth URL using env vars (no TokenStore needed for URL generation)
                auth_url = ""
                try:
                    import os
                    from urllib.parse import urlencode

                    app_id = os.environ.get("FEISHU_APP_ID", "")
                    domain = os.environ.get("FEISHU_DOMAIN", "feishu")
                    base = (
                        "https://open.feishu.cn"
                        if domain == "feishu"
                        else "https://open.larksuite.com"
                    )
                    if app_id:
                        params = {
                            "app_id": app_id,
                            "redirect_uri": "http://localhost:9876/oauth/callback",
                            "state": ctx.user_id,
                        }
                        auth_url = f"{base}/open-apis/authen/v1/authorize?{urlencode(params)}"
                except Exception:
                    pass

                return tool_result_json(
                    error="Feishu authorization required",
                    result=(
                        "This Feishu document requires user authorization. "
                        "Please tell the user to authorize Feishu access."
                    ),
                    data={
                        "auth_required": True,
                        "auth_url": auth_url,
                        "instructions": (
                            "Click the authorization link to grant access, "
                            "then try the request again."
                        ),
                    },
                )
            try:
                resp = await self._get_client().get(
                    url,
                    headers={"Authorization": f"Bearer {ctx.user_token}"},
                )
                if resp.status_code == 401:
                    return tool_result_json(
                        error="Feishu authorization expired",
                        result="Please tell the user to re-authorize Feishu access.",
                    )
                if resp.status_code != 200:
                    return tool_result_json(error=f"Feishu API error: HTTP {resp.status_code}")
            except Exception as e:
                return tool_result_json(error=f"Feishu fetch error: {e}")

            text = self._extract_text(resp.text)[:max_chars]
            title = self._extract_title(resp.text) or url
            return tool_result_json(
                result=f"Fetched Feishu doc: {title}",
                data={"title": title, "text": text, "url": url},
            )

        try:
            resp = await self._get_client().get(url)
            if resp.status_code != 200:
                return tool_result_json(error=f"HTTP {resp.status_code}")

            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type.lower():
                return tool_result_json(error=f"Unsupported content type: {content_type}")

            text = self._extract_text(resp.text)[:max_chars]
            title = self._extract_title(resp.text) or url
            return tool_result_json(
                result=f"Fetched: {title}",
                data={"title": title, "text": text, "url": url},
            )
        except httpx.TimeoutException:
            return tool_result_json(error=f"Timeout fetching {url}")
        except Exception as e:
            return tool_result_json(error=f"Fetch error: {e}")

    @staticmethod
    def _is_feishu_doc_url(url: str) -> bool:
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            if not any(hostname == d or hostname.endswith("." + d) for d in _FEISHU_AUTH_DOMAINS):
                return False
            return parsed.path.startswith(_FEISHU_DOC_PREFIXES)
        except Exception:
            return False

    def _extract_text(self, html: str) -> str:
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<head[^>]*>.*?</head>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<nav[^>]*>.*?</nav>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<footer[^>]*>.*?</footer>", "", html, flags=re.DOTALL | re.IGNORECASE)
        for tag in ["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "br"]:
            html = re.sub(f"</?{tag}[^>]*>", "\n", html, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
        return text.strip()

    def _extract_title(self, html: str) -> str | None:
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return None
