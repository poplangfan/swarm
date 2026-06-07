"""MCP client — connect to external MCP servers and bridge tools."""

from __future__ import annotations

import asyncio
import json
import os

import structlog

from tools.base import ToolBase
from tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)


class MCPClient:
    """Client for connecting to Model Context Protocol (MCP) servers.

    MCP servers expose tools that the agent can use. This client connects
    to external MCP servers and bridges their tools into Swarm's ToolRegistry.
    """

    def __init__(
        self,
        server_name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ):
        self.server_name = server_name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self._process: asyncio.subprocess.Process | None = None
        self._connected = False
        self._tools: dict[str, _MCPToolBridge] = {}

    async def connect(self) -> bool:
        """Start the MCP server process and establish connection."""
        try:
            self._process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **self.env},
            )
            # Send initialize request (JSON-RPC over stdio)
            init_msg = self._build_jsonrpc(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "swarm", "version": "0.1.0"},
                },
            )
            await self._send(init_msg)
            response = await self._receive()
            if response and "result" in response:
                self._connected = True
                logger.info("mcp_connected", server=self.server_name)
                # Discover tools
                await self._discover_tools()
                return True
        except Exception as e:
            logger.error("mcp_connect_failed", server=self.server_name, error=str(e))
        return False

    async def _discover_tools(self) -> None:
        """Query the MCP server for available tools."""
        list_msg = self._build_jsonrpc("tools/list", {})
        await self._send(list_msg)
        response = await self._receive()
        if response and "result" in response:
            for tool_def in response["result"].get("tools", []):
                name = tool_def.get("name", "unknown")
                self._tools[name] = _MCPToolBridge(
                    name=name,
                    description=tool_def.get("description", ""),
                    input_schema=tool_def.get("inputSchema", {}),
                    client=self,
                )
                logger.info("mcp_tool_discovered", server=self.server_name, tool=name)

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call a tool on the MCP server and return the result."""
        if not self._connected:
            return f"Error: MCP server '{self.server_name}' not connected"
        call_msg = self._build_jsonrpc(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
        )
        await self._send(call_msg)
        response = await self._receive()
        if response and "result" in response:
            content = response["result"].get("content", [])
            if isinstance(content, list):
                return "\n".join(c.get("text", str(c)) for c in content if isinstance(c, dict))
            return str(content)
        elif response and "error" in response:
            return f"MCP error: {response['error'].get('message', 'unknown')}"
        return f"No response from MCP tool '{tool_name}'"

    async def register_tools(self, registry: ToolRegistry) -> int:
        """Register all MCP tools into a Swarm ToolRegistry. Returns count."""
        count = 0
        for tool in self._tools.values():
            try:
                registry.register(tool)
                count += 1
            except ValueError:
                pass
        return count

    async def disconnect(self) -> None:
        """Close the MCP server connection."""
        if self._process:
            self._process.stdin.close() if self._process.stdin else None
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
        self._connected = False

    @staticmethod
    def _build_jsonrpc(method: str, params: dict, req_id: int = 1) -> dict:
        return {"jsonrpc": "2.0", "method": method, "params": params, "id": req_id}

    async def _send(self, msg: dict) -> None:
        if self._process and self._process.stdin:
            data = (json.dumps(msg) + "\n").encode()
            self._process.stdin.write(data)
            await self._process.stdin.drain()

    async def _receive(self, timeout: float = 30.0) -> dict | None:
        if self._process and self._process.stdout:
            try:
                line = await asyncio.wait_for(
                    self._process.stdout.readline(),
                    timeout=timeout,
                )
                if line:
                    return json.loads(line.decode())
            except asyncio.TimeoutError:
                pass  # Normal — no message within timeout window
            except json.JSONDecodeError as e:
                logger.warning("mcp_receive_invalid_json", server=self.server_name, error=str(e))
            except Exception as e:
                logger.warning("mcp_receive_error", server=self.server_name, error=str(e))
        return None


class _MCPToolBridge(ToolBase):
    """Bridges an MCP tool into Swarm's ToolBase interface."""

    def __init__(
        self, name: str, description: str, input_schema: dict, client: MCPClient | None = None
    ):
        self.name = name
        self.description = description
        self._input_schema = input_schema
        self._client = client
        # Convert JSON Schema to OpenAI tool parameters format
        self.parameters = {
            "type": "object",
            "properties": input_schema.get("properties", {}),
            "required": input_schema.get("required", []),
        }

    async def execute(self, args: dict, ctx=None) -> str:
        if self._client:
            return await self._client.call_tool(self.name, args)
        return f"Error: MCP tool '{self.name}' not connected"
