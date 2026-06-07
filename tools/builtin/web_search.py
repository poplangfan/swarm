"""Web search tool — DuckDuckGo (free) or Bing API (enterprise)."""

from __future__ import annotations

import re

import httpx

from agent.context import RequestContext
from tools.base import ToolBase, tool_result


class WebSearchTool(ToolBase):
    name = "web_search"
    description = "Search the web for current information"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"},
            "num_results": {"type": "integer", "description": "Max results (1-10)", "default": 5},
        },
        "required": ["query"],
    }

    _shared_client: httpx.AsyncClient | None = None

    def __init__(self, backend: str = "duckduckgo"):
        self._backend = backend

    @classmethod
    def _get_client(cls) -> httpx.AsyncClient:
        if cls._shared_client is None:
            cls._shared_client = httpx.AsyncClient(
                timeout=10.0,
                headers={"User-Agent": "Swarm/1.0"},
            )
        return cls._shared_client

    async def execute(self, args: dict, ctx: RequestContext) -> str:
        query = args.get("query", "")
        num = min(int(args.get("num_results", 5)), 10)
        try:
            if self._backend == "duckduckgo":
                return await self._search_ddg(query, num)
            return tool_result(f"Search backend '{self._backend}' not implemented")
        except Exception as e:
            return tool_result(f"Search failed: {e}")

    async def _search_ddg(self, query: str, num: int) -> str:
        client = self._get_client()
        resp = await client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
        )
        if resp.status_code != 200:
            return tool_result(f"Search returned status {resp.status_code}")
        text = resp.text

        # Multi-level extraction with fallback:
        # 1. Primary: result__snippet class
        # 2. Fallback: result__body class (alternative DDG layout)
        # 3. Last resort: any <a> tag text
        results = self._extract_results(
            text,
            num,
            r'class="result__snippet"[^>]*>(.*?)</a>',
            r'class="result__body"[^>]*>(.*?)</a>',
        )
        if not results:
            return tool_result(f"No results found for '{query}'")
        return "\n".join(results)

    @staticmethod
    def _extract_results(text: str, num: int, *patterns: str) -> list[str]:
        """Try multiple regex patterns in order, return first that yields results."""
        for pattern in patterns:
            snippets = re.findall(pattern, text, re.DOTALL)
            if snippets:
                results = []
                for s in snippets[:num]:
                    clean = re.sub(r"<[^>]+>", "", s).strip()
                    if clean and len(clean) > 5:
                        results.append(f"{len(results) + 1}. {clean}")
                if results:
                    return results
        # Last resort: extract text from any anchor tags
        raw_links = re.findall(r"<a[^>]*>(.*?)</a>", text, re.DOTALL)
        results = []
        for s in raw_links[:num]:
            clean = re.sub(r"<[^>]+>", "", s).strip()
            if clean and len(clean) > 10:
                results.append(f"{len(results) + 1}. {clean}")
        return results
