# Plugin Development Guide

Swarm plugins extend the framework with custom tools, skills, and capabilities.

## Plugin Structure

```
my-plugin/
├── manifest.json       # Plugin metadata
├── __init__.py          # Plugin module
└── tools.py             # Custom tools
```

## Manifest

```json
{
  "schema": "swarm-plugin.v1",
  "name": "feishu-docs",
  "version": "0.1.0",
  "description": "Feishu document operations plugin",
  "capabilities": [
    {
      "type": "tool",
      "provides": ["feishu_doc_read", "feishu_doc_write", "feishu_doc_search"]
    },
    {
      "type": "skill",
      "provides": ["document-collaboration"]
    }
  ],
  "install": {
    "pip": ["feishu-docs-plugin>=0.1.0"]
  },
  "permissions": [
    "drive:drive:read",
    "docx:document:read",
    "docx:document:write"
  ]
}
```

### Manifest Fields

| Field | Required | Description |
|-------|:--------:|-------------|
| `schema` | Yes | Must be `"swarm-plugin.v1"` |
| `name` | Yes | Unique plugin identifier |
| `version` | Yes | Semantic version |
| `description` | Yes | What the plugin does |
| `capabilities` | Yes | Tools, skills, or other features |
| `install` | No | Installation instructions (pip packages) |
| `permissions` | No | Required Feishu OAuth scopes |

## Creating a Plugin Tool

```python
# my_plugin/tools.py
from swarm.tools.base import ToolBase, tool_result
from swarm.agent.context import RequestContext


class FeishuDocSearchTool(ToolBase):
    name = "feishu_doc_search"
    description = "Search the user's Feishu documents"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "limit": {"type": "integer", "description": "Max results", "default": 10},
        },
        "required": ["query"],
    }

    async def execute(self, args: dict, ctx: RequestContext) -> str:
        query = args["query"]
        limit = args.get("limit", 10)

        if not ctx.user_token:
            return tool_result(
                "User authorization required",
                message="Please authorize the app to access your documents"
            )

        # Call Feishu Drive search API with user token
        # ...

        return tool_result(f"Found results for '{query}'")
```

## Registering via Entry Point

In your plugin's `pyproject.toml`:

```toml
[project.entry-points."swarm.plugins"]
feishu_docs = "my_plugin:get_manifest"
```

Or register programmatically:

```python
from swarm.tools.registry import ToolRegistry
from swarm.tools.discovery import discover_entry_point_tools

registry = ToolRegistry()
tools = discover_entry_point_tools("swarm.plugins")
for tool in tools:
    registry.register(tool)
```

## Plugin Lifecycle

```
DISCOVER → VALIDATE → INSTALL → LOAD → ENABLE → DISABLE
```

| State | Description |
|-------|-------------|
| DISCOVERED | Plugin found via filesystem or entry point |
| VALIDATED | Manifest is valid and permissions are acceptable |
| INSTALLED | Dependencies installed via pip |
| LOADED | Module imported, tools/skills registered |
| ENABLED | Plugin is active and serving requests |
| DISABLED | Plugin is inactive but still installed |
| ERROR | Plugin failed during install or load |

## Plugin Development Best Practices

1. **Minimal dependencies**: Keep pip requirements small
2. **Clear error messages**: Help users debug installation issues
3. **Permission scoping**: Only request necessary OAuth scopes
4. **Version compatibility**: Declare compatible Swarm versions
5. **Testing**: Include tests for your plugin tools
6. **Documentation**: Document each tool's parameters and behavior

## Example: Complete Plugin

```python
# my_plugin/__init__.py
"""Feishu Docs Plugin for Swarm."""

def get_manifest():
    return {
        "schema": "swarm-plugin.v1",
        "name": "feishu-docs",
        "version": "0.1.0",
        "description": "Feishu document operations",
        "capabilities": [
            {"type": "tool", "provides": ["doc_search", "doc_read"]}
        ],
        "install": {"pip": []},
        "permissions": ["drive:drive:read"],
    }


def register_tools(registry):
    from my_plugin.tools import FeishuDocSearchTool
    registry.register(FeishuDocSearchTool())
```

## Distributing Plugins

- **PyPI**: Publish as a regular Python package with entry points
- **Git**: Users install via `pip install git+https://...`
- **Local**: Copy plugin directory to Swarm's `plugins/` folder
