"""JSON Schema generation for LLM tool definitions.

NOTE: generate_tool_schema() and validate_tool_args() are reserved for future use.
Current tool definitions are generated via ToolBase.get_definition().
"""

from __future__ import annotations

from typing import Any


# NOTE: reserved for future use — prefer ToolBase.get_definition()
def generate_tool_schema(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    """Generate an OpenAI-compatible tool definition schema.

    Args:
        name: Tool function name.
        description: Tool description for the LLM.
        properties: JSON Schema properties dict.
        required: List of required property names.
    """
    params: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        params["required"] = required
    # Add defaults for any properties without type
    for prop_name, prop_schema in params["properties"].items():
        if "type" not in prop_schema:
            prop_schema["type"] = "string"

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": params,
        },
    }


def validate_tool_args(args: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Validate tool arguments against a schema. Returns list of error messages."""
    errors = []
    params = schema.get("function", {}).get("parameters", {})
    required = set(params.get("required", []))
    properties = params.get("properties", {})

    for req in required:
        if req not in args:
            errors.append(f"Missing required argument: {req}")

    for key, value in args.items():
        if key in properties:
            expected = properties[key].get("type", "string")
            actual = type(value).__name__
            if expected == "string" and not isinstance(value, str):
                errors.append(f"Argument '{key}' should be string, got {actual}")
            elif expected == "integer" and not isinstance(value, int):
                errors.append(f"Argument '{key}' should be integer, got {actual}")
            elif expected == "number" and not isinstance(value, (int, float)):
                errors.append(f"Argument '{key}' should be number, got {actual}")

    return errors
