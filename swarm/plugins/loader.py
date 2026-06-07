"""Plugin loader — discover, validate, install, load plugins."""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import structlog

from swarm.plugins.protocol import PluginManifest, PluginState

logger = structlog.get_logger(__name__)


class PluginLoader:
    """Discovers and manages lifecycle of Swarm plugins.

    Discovery sources:
    1. Filesystem: {plugins_dir}/{plugin_name}/manifest.json
    2. setuptools entry_points: "swarm.plugins" group
    """

    def __init__(self, plugins_dir: Path | None = None):
        self._plugins_dir = Path(plugins_dir) if plugins_dir else Path.cwd() / "plugins"
        self._plugins_dir.mkdir(parents=True, exist_ok=True)
        self._plugins: dict[str, PluginManifest] = {}
        self._modules: dict[str, Any] = {}

    def discover_filesystem(self) -> list[PluginManifest]:
        """Scan the plugins directory for manifests."""
        discovered = []
        for item in self._plugins_dir.iterdir():
            if not item.is_dir():
                continue
            manifest_path = item / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                data = json.loads(manifest_path.read_text())
                manifest = PluginManifest.from_dict(data, source_path=str(item))
                self._plugins[manifest.name] = manifest
                discovered.append(manifest)
                logger.info("plugin_discovered", name=manifest.name, path=str(item))
            except Exception as e:
                logger.warning("plugin_manifest_error", path=str(manifest_path), error=str(e))
        return discovered

    def discover_entry_points(self, group: str = "swarm.plugins") -> list[PluginManifest]:
        """Discover plugins from setuptools entry points."""
        discovered = []
        try:
            from importlib.metadata import entry_points
            for ep in entry_points(group=group):
                try:
                    factory = ep.load()
                    manifest_dict = factory()
                    manifest = PluginManifest.from_dict(manifest_dict)
                    self._plugins[manifest.name] = manifest
                    discovered.append(manifest)
                    logger.info("entry_point_plugin_discovered", name=ep.name)
                except Exception as e:
                    logger.warning("entry_point_plugin_error", name=ep.name, error=str(e))
        except Exception:
            pass
        return discovered

    async def install(self, name: str) -> bool:
        """Install plugin dependencies via pip (async)."""
        manifest = self._plugins.get(name)
        if not manifest:
            return False
        pip_deps = manifest.install.get("pip", [])
        if pip_deps:
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "pip", "install", *pip_deps,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    stderr_text = stderr.decode() if stderr else ""
                    logger.error("plugin_install_failed", name=name,
                                 returncode=proc.returncode,
                                 stderr=stderr_text[:500])
                    manifest.state = PluginState.ERROR
                    return False
            except Exception as e:
                logger.error("plugin_install_error", name=name, error=str(e))
                manifest.state = PluginState.ERROR
                return False
        manifest.state = PluginState.INSTALLED
        return True

    def load(self, name: str) -> Any | None:
        """Load a plugin module and register its capabilities."""
        manifest = self._plugins.get(name)
        if not manifest:
            return None

        module_name = f"swarm_plugin_{name.replace('-', '_')}"
        try:
            mod = importlib.import_module(module_name)
            self._modules[name] = mod
            manifest.state = PluginState.LOADED
            logger.info("plugin_loaded", name=name)
            return mod
        except ImportError:
            logger.warning("plugin_import_failed", name=name, module=module_name)
            manifest.state = PluginState.ERROR
            return None

    def enable(self, name: str) -> bool:
        manifest = self._plugins.get(name)
        if not manifest or manifest.state != PluginState.LOADED:
            return False
        manifest.state = PluginState.ENABLED
        return True

    def disable(self, name: str) -> bool:
        manifest = self._plugins.get(name)
        if not manifest:
            return False
        manifest.state = PluginState.DISABLED
        return True

    def list_plugins(self) -> list[dict]:
        return [p.to_dict() | {"state": p.state.value} for p in self._plugins.values()]
