"""MCP server — expose Swarm tools as an MCP server."""

from __future__ import annotations

from tools.registry import ToolRegistry


class SwarmMCPServer:
    """Expose Swarm's tools via the Model Context Protocol.

    This allows other MCP-compatible agents to use Swarm's tools.
    Uses stdio JSON-RPC transport (same as standard MCP).
    """

    def __init__(self, registry: ToolRegistry, server_name: str = "swarm"):
        self._registry = registry
        self.server_name = server_name

    def list_tools(self) -> list[dict]:
        """List all tools exposed by this MCP server."""
        tools = []
        for name in self._registry.tool_names:
            tool_def = self._registry.get(name)
            if tool_def:
                tools.append(
                    {
                        "name": tool_def.name,
                        "description": tool_def.description,
                        "inputSchema": tool_def.schema.get("parameters", tool_def.schema),
                    }
                )
        return tools

    async def call_tool(self, name: str, arguments: dict) -> str:
        """Execute a tool via MCP call."""
        return await self._registry.execute(name, arguments)
