"""Tests for plugin system — manifest protocol, loader discovery."""

import json
import tempfile
from pathlib import Path

from plugins.loader import PluginLoader
from plugins.protocol import PluginManifest, PluginState


class TestPluginManifest:
    def test_from_dict(self):
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "description": "A test plugin",
            "capabilities": [{"type": "tool", "provides": ["test_tool"]}],
            "install": {"pip": ["test-pkg>=1.0"]},
            "permissions": ["im:message"],
        }
        manifest = PluginManifest.from_dict(data, source_path="/tmp/test")
        assert manifest.name == "test-plugin"
        assert manifest.version == "1.0.0"
        assert len(manifest.capabilities) == 1
        assert manifest.capabilities[0]["type"] == "tool"
        assert manifest.state == PluginState.DISCOVERED

    def test_to_dict(self):
        manifest = PluginManifest(
            name="test",
            version="0.1.0",
            description="Test",
            capabilities=[{"type": "tool", "provides": ["echo"]}],
        )
        d = manifest.to_dict()
        assert d["schema"] == "swarm-plugin.v1"
        assert d["name"] == "test"
        assert len(d["capabilities"]) == 1

    def test_state_transitions(self):
        manifest = PluginManifest(name="test")
        assert manifest.state == PluginState.DISCOVERED
        manifest.state = PluginState.INSTALLED
        assert manifest.state == PluginState.INSTALLED
        manifest.state = PluginState.LOADED
        assert manifest.state == PluginState.LOADED
        manifest.state = PluginState.ENABLED
        assert manifest.state == PluginState.ENABLED
        manifest.state = PluginState.DISABLED
        assert manifest.state == PluginState.DISABLED

    def test_minimal_manifest(self):
        manifest = PluginManifest(name="minimal")
        assert manifest.version == "0.1.0"
        assert manifest.description == ""
        assert manifest.capabilities == []
        assert manifest.state == PluginState.DISCOVERED


class TestPluginLoader:
    def test_discover_from_filesystem(self):
        with tempfile.TemporaryDirectory() as d:
            plugins_dir = Path(d) / "plugins"
            plugins_dir.mkdir()

            plugin_dir = plugins_dir / "my-plugin"
            plugin_dir.mkdir()
            manifest_data = {
                "name": "my-plugin",
                "version": "1.0.0",
                "description": "My custom plugin",
                "capabilities": [],
                "install": {},
                "permissions": [],
            }
            (plugin_dir / "manifest.json").write_text(json.dumps(manifest_data))

            loader = PluginLoader(plugins_dir)
            discovered = loader.discover_filesystem()
            assert len(discovered) == 1
            assert discovered[0].name == "my-plugin"

    def test_discover_empty_directory(self):
        with tempfile.TemporaryDirectory() as d:
            plugins_dir = Path(d) / "plugins"
            plugins_dir.mkdir()
            loader = PluginLoader(plugins_dir)
            discovered = loader.discover_filesystem()
            assert len(discovered) == 0

    def test_discover_invalid_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            plugins_dir = Path(d) / "plugins"
            plugins_dir.mkdir()
            plugin_dir = plugins_dir / "broken-plugin"
            plugin_dir.mkdir()
            (plugin_dir / "manifest.json").write_text("not valid json {{{")

            loader = PluginLoader(plugins_dir)
            # Should not crash on invalid manifests
            discovered = loader.discover_filesystem()
            assert len(discovered) == 0

    def test_list_plugins(self):
        with tempfile.TemporaryDirectory() as d:
            plugins_dir = Path(d) / "plugins"
            plugins_dir.mkdir()
            plugin_dir = plugins_dir / "list-test"
            plugin_dir.mkdir()
            (plugin_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "name": "list-test",
                        "version": "1.0",
                        "description": "For listing",
                        "capabilities": [{"type": "skill", "provides": ["test"]}],
                    }
                )
            )

            loader = PluginLoader(plugins_dir)
            loader.discover_filesystem()
            plugins = loader.list_plugins()
            assert len(plugins) == 1
            assert plugins[0]["name"] == "list-test"

    def test_disable_plugin(self):
        with tempfile.TemporaryDirectory() as d:
            plugins_dir = Path(d) / "plugins"
            plugins_dir.mkdir()
            plugin_dir = plugins_dir / "disable-test"
            plugin_dir.mkdir()
            (plugin_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "name": "disable-test",
                        "version": "1.0",
                        "description": "For disabling",
                        "capabilities": [],
                    }
                )
            )

            loader = PluginLoader(plugins_dir)
            loader.discover_filesystem()
            assert loader.disable("disable-test")
            assert not loader.disable("nonexistent")
