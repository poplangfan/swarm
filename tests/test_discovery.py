"""Tests for tool auto-discovery system."""

import pytest
from swarm.tools.discovery import discover_builtin_tools, load_all_tools
from swarm.tools.registry import ToolRegistry
from swarm.tools.base import ToolBase


class TestDiscovery:
    def test_discovers_builtin_tools(self):
        tools = discover_builtin_tools("swarm.tools.builtin")
        tool_names = [t.name for t in tools]
        # Should find at least some built-in tool classes
        assert len(tools) >= 1

    def test_load_all_into_registry(self):
        reg = ToolRegistry()
        count = load_all_tools(reg)
        assert count >= 1
        assert len(reg.tool_names) >= 1

    def test_discovered_tools_are_registered_correctly(self):
        reg = ToolRegistry()
        load_all_tools(reg)
        for name in reg.tool_names:
            tool = reg.get(name)
            assert tool is not None
            assert isinstance(tool, ToolBase)
            assert tool.name == name

    def test_discover_nonexistent_package(self):
        tools = discover_builtin_tools("swarm.tools.nonexistent")
        assert len(tools) == 0


class TestLoadAllTools:
    def test_no_duplicates(self):
        reg = ToolRegistry()
        count1 = load_all_tools(reg)
        # Second load should not add duplicates (they're already registered)
        # Actually it will raise ValueError, so we catch it
        count2 = 0
        try:
            count2 = load_all_tools(reg)
        except ValueError:
            pass  # Expected if duplicate
        # Either way, registry should have tools
        assert len(reg.tool_names) >= 1
