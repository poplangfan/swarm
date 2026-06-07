# Tools Guide

Swarm's tool system allows the LLM to perform actions beyond text generation — searching the web, sending messages, managing files, and more.

## Built-in Tools

| Tool | Description |
|------|-------------|
| `web_search` | Search the web via DuckDuckGo or Bing |
| `web_fetch` | Fetch and extract content from URLs |
| `feishu_message` | Send messages and reactions in Feishu |
| `feishu_file` | List and manage Feishu Drive files |
| `cron_manage` | Create, list, delete scheduled tasks |
| `system_command` | Built-in system commands (help, status) |

## How Tools Work

1. **Definition**: Each tool defines a name, description, and JSON Schema parameters
2. **Registration**: Tools are registered in the `ToolRegistry`
3. **LLM Call**: Tool definitions are sent to the LLM with each request
4. **Execution**: When the LLM returns a tool call, Swarm executes it
5. **Result Injection**: The result is added to the conversation

```
User: "What's the weather in Beijing?"
  → LLM decides: need web_search tool
  → LLM returns: tool_call(name="web_search", args={"query": "Beijing weather"})
  → Swarm executes: web_search("Beijing weather")
  → Result injected into conversation
  → LLM reads result and forms answer
  → User receives: "Beijing weather today: Sunny, 15°C"
```

## Creating a Custom Tool

```python
from swarm.tools.base import ToolBase, tool_result
from swarm.agent.context import RequestContext


class MyCustomTool(ToolBase):
    """Description shown to the LLM."""

    # Unique identifier for the tool
    name = "my_tool"

    # Description helps the LLM decide when to use it
    description = "What this tool does and when to use it"

    # JSON Schema for parameters (OpenAI format)
    parameters = {
        "type": "object",
        "properties": {
            "param1": {
                "type": "string",
                "description": "Description of parameter 1",
            },
            "param2": {
                "type": "integer",
                "description": "Description of parameter 2",
                "default": 10,
            },
        },
        "required": ["param1"],
    }

    async def execute(self, args: dict, ctx: RequestContext) -> str:
        """Execute the tool with the given arguments.

        Args:
            args: Validated arguments from the LLM
            ctx: Request context (chat_id, user_id, user_token)

        Returns:
            A result string the LLM can understand
        """
        param1 = args.get("param1", "default")
        param2 = args.get("param2", 10)

        # Do your work here...
        result = f"Processed {param1} with value {param2}"

        return tool_result(result)
```

## Registering Tools

```python
from swarm.tools.registry import ToolRegistry
from my_tools import MyCustomTool

registry = ToolRegistry()
registry.register(MyCustomTool())

# Or auto-discover from a package
from swarm.tools.discovery import load_all_tools
load_all_tools(registry)
```

## Permission Model

Tools can declare required permissions:

```python
from swarm.tools.permission import Permission

class AdminTool(ToolBase):
    name = "admin_delete"
    permissions = {"admin:delete"}

    async def execute(self, args, ctx):
        # ctx.permissions is checked before execution
        ...
```

## Best Practices

1. **Clear descriptions**: The LLM reads your description to decide when to call the tool
2. **Validate inputs**: Check argument types and ranges
3. **Handle errors gracefully**: Return error messages the LLM can understand
4. **Keep results focused**: Return relevant data, not raw API responses
5. **Use tool_result()**: Wraps results in LLM-friendly format
6. **Respect timeouts**: Long-running operations should use subagents

## Tool Schema Generation

Use the `generate_tool_schema` helper for clean schema definitions:

```python
from swarm.tools.schema import generate_tool_schema

schema = generate_tool_schema(
    name="weather",
    description="Get weather for a city",
    properties={
        "city": {"type": "string", "description": "City name"},
        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
    },
    required=["city"],
)
```

## Plugin Tools

Tools from plugins are discovered via setuptools entry points:

```python
# In plugin's pyproject.toml:
[project.entry-points."swarm.plugins"]
my_plugin = "my_plugin:create_tool"
```

Swarm auto-discovers and loads plugin tools on startup.
