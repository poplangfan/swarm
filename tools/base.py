"""Tool base class and utilities."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from agent.context import RequestContext


def tool_result(message: str, **kwargs) -> str:
    """Format a tool execution result as a string the LLM can understand."""
    if kwargs:
        parts = [message]
        for key, value in kwargs.items():
            parts.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        return "\n".join(parts)
    return message


class ToolBase(ABC):
    """Base class for all Swarm tools."""

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {"type": "object", "properties": {}}
    permissions: set[str] = set()

    def get_definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @abstractmethod
    async def execute(self, args: dict[str, Any], ctx: RequestContext) -> str:
        ...

    def check_permission(self, ctx: RequestContext) -> bool:
        if not self.permissions:
            return True
        return bool(self.permissions & ctx.permissions)
