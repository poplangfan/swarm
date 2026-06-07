"""Plugin manifest protocol — install, enable, disable lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PluginState(Enum):
    DISCOVERED = "discovered"
    INSTALLED = "installed"
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass
class PluginManifest:
    """A plugin manifest describing capabilities, install steps, and permissions."""

    name: str
    version: str = "0.1.0"
    description: str = ""
    capabilities: list[dict[str, Any]] = field(default_factory=list)
    install: dict[str, Any] = field(default_factory=dict)
    permissions: list[str] = field(default_factory=list)
    state: PluginState = PluginState.DISCOVERED
    source_path: str = ""

    @classmethod
    def from_dict(cls, data: dict, source_path: str = "") -> PluginManifest:
        return cls(
            name=data.get("name", "unknown"),
            version=data.get("version", "0.1.0"),
            description=data.get("description", ""),
            capabilities=data.get("capabilities", []),
            install=data.get("install", {}),
            permissions=data.get("permissions", []),
            source_path=source_path,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "swarm-plugin.v1",
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "capabilities": self.capabilities,
            "install": self.install,
            "permissions": self.permissions,
        }
