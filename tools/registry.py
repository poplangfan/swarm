"""Tool registry — registration, lookup, execution, LLM definitions."""

from __future__ import annotations

from typing import Any

import structlog

from agent.context import RequestContext
from tools.base import ToolBase, tool_result

logger = structlog.get_logger(__name__)


class ToolRegistry:
    """Central registry for all tools."""

    def __init__(self):
        self._tools: dict[str, ToolBase] = {}

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def register(self, tool: ToolBase) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
        logger.debug("tool_registered", name=tool.name)

    def unregister(self, name: str) -> bool:
        """Remove a tool from the registry. Returns True if removed."""
        if name in self._tools:
            del self._tools[name]
            logger.debug("tool_unregistered", name=name)
            return True
        return False

    def get(self, name: str) -> ToolBase | None:
        return self._tools.get(name)

    def get_definitions(self, ctx: RequestContext | None = None) -> list[dict[str, Any]]:
        # No context = no trust — don't expose any tool definitions
        if ctx is None:
            return []
        defs = []
        for tool in self._tools.values():
            if not tool.check_permission(ctx):
                continue
            defs.append(tool.get_definition())
        return defs

    async def execute(
        self, name: str, args: dict[str, Any], ctx: RequestContext | None = None
    ) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return tool_result(f"Error: unknown tool '{name}'")
        # Provide a minimal fallback context for execution paths without one
        # (e.g., MCP server, cron jobs). Full permissions require a real context.
        if ctx is None:
            ctx = RequestContext(
                trace_id="unknown",
                chat_id="unknown",
                chat_type="p2p",
                user_id="unknown",
                message_id="unknown",
            )
        if not tool.check_permission(ctx):
            return tool_result(f"Error: permission denied for tool '{name}'")
        logger.info("tool_executing", name=name)
        try:
            return await tool.execute(args, ctx)
        except Exception as e:
            logger.error("tool_failed", name=name, error=str(e))
            return tool_result(f"Error: {e}")
