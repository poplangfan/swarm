"""Web fetch tool — fetch URL content and convert to markdown text."""

from __future__ import annotations

import re

import httpx

from swarm.agent.context import RequestContext
from swarm.tools.base import ToolBase, tool_result


class WebFetchTool(ToolBase):
    name = "web_fetch"
    description = "Fetch content from a URL and extract the readable text"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to fetch"},
            "max_chars": {"type": "integer", "description": "Max characters to return", "default": 8000},
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

    def _extract_text(self, html: str) -> str:
        """Extract readable text from HTML."""
        # Remove scripts, styles, and metadata
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<head[^>]*>.*?</head>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # Replace block elements with newlines
        for tag in ['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'tr', 'br']:
            html = re.sub(f'</?{tag}[^>]*>', '\n', html, flags=re.IGNORECASE)

        # Strip remaining tags
        text = re.sub(r'<[^>]+>', ' ', html)
        # Collapse whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Decode HTML entities
        text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')

        return text.strip()

    def _extract_title(self, html: str) -> str | None:
        """Extract the page title from HTML."""
        match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return None
