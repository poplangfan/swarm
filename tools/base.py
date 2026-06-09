"""Tool base class and utilities — Hermes-pattern tool interface."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from agent.context import RequestContext


def tool_result(message: str, **kwargs) -> str:
    """Format a tool execution result as a string the LLM can understand.

    Kept for backward compatibility. Prefer tool_result_json() for new tools.
    """
    if kwargs:
        parts = [message]
        for key, value in kwargs.items():
            parts.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        return "\n".join(parts)
    return message


def tool_result_json(
    result: str = "",
    error: str = "",
    data: Any = None,
    **kwargs,
) -> str:
    """Format a tool execution result as a JSON string.

    Hermes pattern: all tool results are JSON strings. This gives the LLM
    a consistent interface and allows structured error propagation.

    Args:
        result: Success message or summary.
        error: Error message. If set, indicates the tool call failed.
        data: Arbitrary structured data to include in the response.
        **kwargs: Additional key-value pairs merged into the response.
    """
    response: dict[str, Any] = {"success": not bool(error)}
    if result:
        response["result"] = result
    if error:
        response["error"] = error
    if data is not None:
        response["data"] = data
    response.update(kwargs)
    return json.dumps(response, ensure_ascii=False, default=str)


class ToolBase(ABC):
    """Base class for all Swarm tools.

    Tools declare:
    - name: unique identifier used in LLM function calls
    - description: human-readable description for the LLM
    - parameters: JSON Schema for the tool's arguments
    - toolset: which toolset group this tool belongs to (default: "core")
    - permissions: set of Permission strings required (optional)
    """

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {"type": "object", "properties": {}}
    toolset: str = "core"
    permissions: set[str] = set()

    @classmethod
    def check_requirements(cls) -> bool:
        """Return True if this tool's runtime requirements are met.

        Override in subclasses to check for installed packages, env vars, etc.
        Tools whose requirements are not met will NOT be disclosed to the LLM.
        """
        return True

    @classmethod
    def required_env_vars(cls) -> list[str]:
        """List of environment variable names required by this tool.

        Override in subclasses. Used together with check_requirements().
        """
        return []

    def get_definition(self) -> dict[str, Any]:
        """Generate an OpenAI-compatible tool function definition."""
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
        """Execute the tool. Must return a string (preferably JSON).

        All implementations should use tool_result_json() to maintain
        the Hermes pattern of consistent JSON tool outputs.
        """
        ...

    def check_permission(self, ctx: RequestContext) -> bool:
        """Check if the tool is allowed for this request context."""
        if not self.permissions:
            return True
        return bool(self.permissions & ctx.permissions)
