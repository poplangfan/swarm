"""Tool registry - registration, lookup, execution, LLM definitions.

Hermes-pattern: tools register themselves at import time via registry.register().
Each tool declares its toolset, JSON Schema, handler, check function, and environment
requirements. Only tools whose requirements are met are disclosed to the LLM.
"""

from __future__ import annotations

import os
from typing import Any, Callable

import structlog

from agent.context import RequestContext
from tools.base import ToolBase, tool_result_json

logger = structlog.get_logger(__name__)


class ToolDef:
    """Metadata for a registered tool, including schema and runtime checks."""

    def __init__(
        self,
        name: str,
        toolset: str,
        schema: dict[str, Any],
        handler: Callable,
        check_fn: Callable[[], bool] | None = None,
        requires_env: list[str] | None = None,
        description: str = "",
        cls: type[ToolBase] | None = None,
        instance: ToolBase | None = None,
    ) -> None:
        self.name = name
        self.toolset = toolset
        self.schema = schema
        self.handler = handler
        self.check_fn = check_fn
        self.requires_env = requires_env or []
        self.description = description
        self.cls = cls
        self._instance = instance

    @property
    def instance(self) -> ToolBase | None:
        """Return the cached ToolBase instance, creating from cls if needed."""
        if self._instance is None and self.cls is not None:
            try:
                self._instance = self.cls()
            except Exception as e:
                logger.warning("tool_instantiate_failed", name=self.name, error=str(e))
        return self._instance

    def check_requirements(self) -> bool:
        """Return True if all environment requirements are met."""
        if self.check_fn is not None:
            try:
                if not self.check_fn():
                    logger.debug("tool_check_fn_failed", name=self.name)
                    return False
            except Exception as e:
                logger.warning("tool_check_fn_error", name=self.name, error=str(e))
                return False

        for env_var in self.requires_env:
            if not os.environ.get(env_var):
                logger.debug("tool_env_missing", name=self.name, env_var=env_var)
                return False

        return True

    def get_definition(self) -> dict[str, Any]:
        """Generate an OpenAI-compatible tool function definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description or self.schema.get("description", ""),
                "parameters": self.schema.get("parameters", self.schema),
            },
        }


class ToolRegistry:
    """Central registry for all tools, patterned on Hermes Agent."""

    def __init__(self) -> None:
        self._defs: dict[str, ToolDef] = {}
        self._enabled_toolsets: set[str] = set()

    @property
    def enabled_toolsets(self) -> set[str]:
        return self._enabled_toolsets

    def enable_toolsets(self, toolsets: set[str] | list[str]) -> None:
        self._enabled_toolsets = set(toolsets)

    @property
    def tool_names(self) -> list[str]:
        return list(self._defs.keys())

    def register(
        self,
        name_or_tool: str | ToolBase,
        toolset: str = "",
        schema: dict[str, Any] | None = None,
        handler: Callable | None = None,
        description: str = "",
        check_fn: Callable[[], bool] | None = None,
        requires_env: list[str] | None = None,
        tool_cls: type[ToolBase] | None = None,
        tool_instance: ToolBase | None = None,
    ) -> None:
        """Register a tool.

        Two calling conventions:
        1. register(tool_instance) - backward compat, delegates to register_tool()
        2. register(name, toolset, schema, handler, ...) - new API
        """
        # Backward compatibility: called with a ToolBase instance
        if isinstance(name_or_tool, ToolBase):
            self.register_tool(name_or_tool)
            return

        name = name_or_tool
        if not schema or not handler:
            raise ValueError(f"Tool '{name}' missing schema or handler")
        if name in self._defs:
            raise ValueError(f"Tool '{name}' already registered")

        self._defs[name] = ToolDef(
            name=name,
            toolset=toolset,
            schema=schema,
            handler=handler,
            check_fn=check_fn,
            requires_env=requires_env or [],
            description=description,
            cls=tool_cls,
            instance=tool_instance,
        )
        logger.debug("tool_registered", name=name, toolset=toolset)

    def register_tool(self, tool: ToolBase) -> None:
        """Register a ToolBase instance using the classic interface."""
        if tool.name in self._defs:
            raise ValueError(f"Tool '{tool.name}' already registered")

        async def _handler(args, ctx):
            return await tool.execute(args, ctx)

        self.register(
            name_or_tool=tool.name,
            toolset=getattr(tool, "toolset", "core"),
            schema={
                "description": tool.description,
                "parameters": tool.parameters,
            },
            handler=_handler,
            description=tool.description,
            tool_instance=tool,
        )

    def unregister(self, name: str) -> bool:
        if name in self._defs:
            del self._defs[name]
            logger.debug("tool_unregistered", name=name)
            return True
        return False

    def get(self, name: str) -> ToolDef | None:
        return self._defs.get(name)

    def get_definitions(self, ctx: RequestContext | None = None) -> list[dict[str, Any]]:
        """Return tool definitions for LLM disclosure.

        Filters: ctx=None -> empty, toolset membership, requirement checks.
        """
        if ctx is None:
            return []

        defs: list[dict[str, Any]] = []
        for tool_def in self._defs.values():
            if self._enabled_toolsets and tool_def.toolset not in self._enabled_toolsets:
                continue
            if not tool_def.check_requirements():
                continue
            defs.append(tool_def.get_definition())
        return defs

    async def execute(
        self, name: str, args: dict[str, Any], ctx: RequestContext | None = None
    ) -> str:
        """Execute a tool by name, returning a JSON result string."""
        tool_def = self._defs.get(name)
        if tool_def is None:
            return tool_result_json(error=f"Unknown tool: {name}")

        if ctx is None:
            ctx = RequestContext(
                trace_id="unknown",
                chat_id="unknown",
                chat_type="p2p",
                user_id="unknown",
                message_id="unknown",
            )

        if not tool_def.check_requirements():
            return tool_result_json(error=f"Tool '{name}' requirements not met")

        logger.info("tool_executing", name=name, toolset=tool_def.toolset)

        try:
            result = await tool_def.handler(args, ctx)
            if not isinstance(result, str):
                import json as _json

                result = _json.dumps(result, ensure_ascii=False)
            return result
        except Exception as e:
            from utils.error_classifier import sanitize_tool_error

            clean_error = sanitize_tool_error(e)
            logger.error("tool_failed", name=name, error=str(e))
            return tool_result_json(error=clean_error)
