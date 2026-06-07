"""Tests for MCP client and server bridge."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from swarm.mcp.client import MCPClient, _MCPToolBridge
from swarm.mcp.server import SwarmMCPServer
from swarm.tools.registry import ToolRegistry
from swarm.tools.base import ToolBase


class TestMCPToolBridge:
    def test_tool_definition(self):
        bridge = _MCPToolBridge(
            name="test_tool",
            description="A test MCP tool",
            input_schema={
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )
        assert bridge.name == "test_tool"
        assert bridge.description == "A test MCP tool"
        assert "query" in bridge.parameters["properties"]

    @pytest.mark.asyncio
    async def test_execute_without_client(self):
        bridge = _MCPToolBridge(
            name="test_tool",
            description="Test",
            input_schema={},
        )
        result = await bridge.execute({"key": "value"})
        assert "not connected" in result.lower()

    @pytest.mark.asyncio
    async def test_execute_with_client(self):
        mock_client = MagicMock()
        mock_client.call_tool = AsyncMock(return_value="Tool result")

        bridge = _MCPToolBridge(
            name="test_tool",
            description="Test",
            input_schema={},
            client=mock_client,
        )
        result = await bridge.execute({"key": "value"})
        assert result == "Tool result"
        mock_client.call_tool.assert_called_once()


class TestSwarmMCPServer:
    def test_list_tools(self):
        reg = ToolRegistry()

        class EchoTool(ToolBase):
            name = "echo"
            description = "Echo back"
            parameters = {"type": "object", "properties": {}}
            async def execute(self, args, ctx):
                return str(args)

        reg.register(EchoTool())
        server = SwarmMCPServer(reg, server_name="test_server")

        tools = server.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "echo"
        assert "description" in tools[0]
        assert "inputSchema" in tools[0]

    @pytest.mark.asyncio
    async def test_call_tool(self):
        reg = ToolRegistry()

        class CalcTool(ToolBase):
            name = "add"
            description = "Add numbers"
            parameters = {
                "type": "object",
                "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                "required": ["a", "b"],
            }
            async def execute(self, args, ctx):
                return str(args["a"] + args["b"])

        reg.register(CalcTool())
        server = SwarmMCPServer(reg)

        result = await server.call_tool("add", {"a": 3, "b": 4})
        assert "7" in result

    def test_empty_registry(self):
        reg = ToolRegistry()
        server = SwarmMCPServer(reg)
        assert len(server.list_tools()) == 0


class TestMCPClientConstruction:
    def test_client_init(self):
        client = MCPClient(
            server_name="test-server",
            command="python",
            args=["-m", "test_server"],
            env={"TEST": "value"},
        )
        assert client.server_name == "test-server"
        assert client.command == "python"
        assert client.env.get("TEST") == "value"

    def test_jsonrpc_message_building(self):
        msg = MCPClient._build_jsonrpc("initialize", {"protocolVersion": "2024-11-05"})
        assert msg["jsonrpc"] == "2.0"
        assert msg["method"] == "initialize"
        assert "protocolVersion" in msg["params"]
        assert msg["id"] == 1
