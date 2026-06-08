"""Web fetch tool — fetch URL content and convert to markdown text."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from agent.context import RequestContext
from tools.base import ToolBase, tool_result

# Domains that require Feishu OAuth to access content
_FEISHU_AUTH_DOMAINS = {
    "horizonrobotics.feishu.cn",
    "feishu.cn",
    "larksuite.com",
}

# Path prefixes that indicate Feishu document/wiki/bitable content
_FEISHU_DOC_PREFIXES = ("/wiki/", "/docs/", "/base/", "/sheet/", "/mindnotes/")


class WebFetchTool(ToolBase):
    name = "web_fetch"
    description = "Fetch content from a URL and extract the readable text"
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
            return tool_result(f"Invalid URL: {url}")

        # Detect Feishu document URLs that require OAuth
        if self._is_feishu_doc_url(url):
            if not ctx.user_token:
                return tool_result(
                    "This Feishu document requires user authorization. "
                    "Please tell the user to authorize Feishu access first. "
                    "The bot should guide the user by saying: "
                    '"To access Feishu documents, you need to authorize first. '
                    "Please use the /auth command or visit the authorization link I'll provide. "
                    'After authorizing, try the request again."'
                )

            # Use user token to fetch Feishu doc content
            try:
                resp = await self._get_client().get(
                    url,
                    headers={"Authorization": f"Bearer {ctx.user_token}"},
                )
                if resp.status_code == 401:
                    return tool_result(
                        "Feishu authorization expired. "
                        "Please tell the user to re-authorize Feishu access."
                    )
                if resp.status_code != 200:
                    return tool_result(f"Feishu API error: HTTP {resp.status_code}")
            except Exception as e:
                return tool_result(f"Feishu fetch error: {e}")

            text = self._extract_text(resp.text)
            if len(text) > max_chars:
                text = text[:max_chars] + "\n\n... [truncated]"
            title = self._extract_title(resp.text) or url
            return tool_result(f"Fetched Feishu doc: {title}", content=text)

        try:
            resp = await self._get_client().get(url)
            if resp.status_code != 200:
                return tool_result(f"HTTP {resp.status_code}")

            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type.lower():
                return tool_result(f"Unsupported content type: {content_type}")

            text = self._extract_text(resp.text)
            if len(text) > max_chars:
                text = text[:max_chars] + "\n\n... [truncated]"

            title = self._extract_title(resp.text) or url
            return tool_result(f"Fetched: {title}", content=text)
        except httpx.TimeoutException:
            return tool_result(f"Timeout fetching {url}")
        except Exception as e:
            return tool_result(f"Fetch error: {e}")

    @staticmethod
    def _is_feishu_doc_url(url: str) -> bool:
        """Check if a URL points to a Feishu document/wiki/bitable that needs OAuth."""
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            # Check if any Feishu auth domain matches
            if not any(hostname == d or hostname.endswith("." + d) for d in _FEISHU_AUTH_DOMAINS):
                return False
            # Check if path indicates a document/wiki/bitable
            return parsed.path.startswith(_FEISHU_DOC_PREFIXES)
        except Exception:
            return False

    def _extract_text(self, html: str) -> str:
        """Extract readable text from HTML."""
        # Remove scripts, styles, and metadata
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<head[^>]*>.*?</head>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<nav[^>]*>.*?</nav>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<footer[^>]*>.*?</footer>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Replace block elements with newlines
        for tag in ["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "br"]:
            html = re.sub(f"</?{tag}[^>]*>", "\n", html, flags=re.IGNORECASE)

        # Strip remaining tags
        text = re.sub(r"<[^>]+>", " ", html)
        # Collapse whitespace
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Decode HTML entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")

        return text.strip()

    def _extract_title(self, html: str) -> str | None:
        """Extract the page title from HTML."""
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return None
