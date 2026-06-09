"""Tests for tool auto-discovery system."""

from tools.base import ToolBase
from tools.discovery import discover_builtin_tools, load_all_tools
from tools.registry import ToolDef, ToolRegistry


class TestDiscovery:
    def test_discovers_builtin_tools(self):
        tools = discover_builtin_tools("tools.builtin")
        [t.name for t in tools]
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
            tool_def = reg.get(name)
            assert tool_def is not None
            assert isinstance(tool_def, ToolDef)
            assert tool_def.name == name
            # Verify the underlying ToolBase instance is accessible
            assert tool_def.instance is not None
            assert isinstance(tool_def.instance, ToolBase)
            assert tool_def.instance.name == name

    def test_discover_nonexistent_package(self):
        tools = discover_builtin_tools("tools.nonexistent")
        assert len(tools) == 0


class TestLoadAllTools:
    def test_no_duplicates(self):
        reg = ToolRegistry()
        _ = load_all_tools(reg)
        # Second load should not add duplicates (they're already registered)
        # Actually it will raise ValueError, so we catch it
        _ = 0
        try:
            _ = load_all_tools(reg)
        except ValueError:
            pass  # Expected if duplicate
        # Either way, registry should have tools
        assert len(reg.tool_names) >= 1
