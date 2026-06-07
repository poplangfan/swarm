"""Tests for tools system."""

import pytest
from swarm.tools.base import tool_result, ToolBase
from swarm.tools.registry import ToolRegistry
from swarm.agent.context import RequestContext


class EchoTool(ToolBase):
    name = "echo"
    description = "Echo input text"
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }
    async def execute(self, args, ctx):
        return tool_result(args.get("text", ""))


class TestToolRegistry:
    def test_register_and_list(self):
        reg = ToolRegistry()
        reg.register(EchoTool())
        assert "echo" in reg.tool_names

    def test_get_definitions(self):
        reg = ToolRegistry()
        reg.register(EchoTool())
        defs = reg.get_definitions()
        # No context = no trust — definitions should be empty
        assert len(defs) == 0

    def test_get_definitions_with_ctx(self, sample_ctx):
        reg = ToolRegistry()
        reg.register(EchoTool())
        defs = reg.get_definitions(sample_ctx)
        assert len(defs) == 1
        assert defs[0]["function"]["name"] == "echo"

    def test_unregister(self):
        reg = ToolRegistry()
        reg.register(EchoTool())
        assert "echo" in reg.tool_names
        assert reg.unregister("echo") is True
        assert "echo" not in reg.tool_names

    def test_unregister_nonexistent(self):
        reg = ToolRegistry()
        assert reg.unregister("nonexistent") is False

    @pytest.mark.asyncio
    async def test_execute(self, sample_ctx):
        reg = ToolRegistry()
        reg.register(EchoTool())
        result = await reg.execute("echo", {"text": "hello"})
        assert "hello" in result

    def test_duplicate_register(self):
        reg = ToolRegistry()
        reg.register(EchoTool())
        with pytest.raises(ValueError):
            reg.register(EchoTool())

    @pytest.mark.asyncio
    async def test_unknown_tool(self, sample_ctx):
        reg = ToolRegistry()
        result = await reg.execute("nonexistent", {})
        assert "unknown" in result.lower()


def test_tool_result_formatting():
    r = tool_result("success", data={"key": "value"})
    assert "success" in r
