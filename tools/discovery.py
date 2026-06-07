"""Tool auto-discovery — pkgutil scanning + setuptools entry-points."""

from __future__ import annotations

import importlib
import pkgutil

import structlog

from tools.base import ToolBase
from tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)


def discover_builtin_tools(package_path: str = "tools.builtin") -> list[type[ToolBase]]:
    """Auto-discover ToolBase subclasses in a package via pkgutil."""
    tools: list[type[ToolBase]] = []
    try:
        package = importlib.import_module(package_path)
        for _, module_name, is_pkg in pkgutil.iter_modules(
            package.__path__, package.__name__ + "."
        ):
            if is_pkg:
                continue
            try:
                mod = importlib.import_module(module_name)
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, ToolBase)
                        and attr is not ToolBase
                    ):
                        tools.append(attr)
                        logger.debug("discovered_tool", tool=attr_name, module=module_name)
            except Exception as e:
                logger.warning("tool_discovery_error", module=module_name, error=str(e))
    except ModuleNotFoundError:
        logger.debug("package_not_found", package=package_path)
    return tools


def discover_entry_point_tools(group: str = "swarm.plugins") -> list[ToolBase]:
    """Discover tools from setuptools entry-points."""
    tools: list[ToolBase] = []
    try:
        from importlib.metadata import entry_points

        eps = entry_points(group=group)
        for ep in eps:
            try:
                factory = ep.load()
                tool = factory()
                if isinstance(tool, ToolBase):
                    tools.append(tool)
                    logger.info("entry_point_tool_loaded", name=ep.name, group=group)
            except Exception as e:
                logger.warning("entry_point_load_error", name=ep.name, error=str(e))
    except Exception:
        pass
    return tools


def load_all_tools(registry: ToolRegistry) -> int:
    """Discover and register all tools (builtin + entry-points). Returns count."""
    count = 0
    for tool_cls in discover_builtin_tools():
        try:
            registry.register(tool_cls())
            count += 1
        except (ValueError, Exception) as e:
            logger.warning("tool_load_skip", tool=tool_cls.__name__, error=str(e))

    for tool in discover_entry_point_tools():
        try:
            registry.register(tool)
            count += 1
        except (ValueError, Exception) as e:
            logger.warning("plugin_tool_load_skip", tool=tool.name, error=str(e))

    logger.info("tools_loaded", count=count)
    return count
