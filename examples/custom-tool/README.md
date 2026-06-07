# Custom Tool Example

Add a custom tool to your Swarm bot.

## Files

- `my_tools.py` — Custom tool definition
- `config.yaml` — Configuration with custom tool enabled

## The Tool

This example adds a `weather` tool that the LLM can call:

```python
class WeatherTool(ToolBase):
    name = "get_weather"
    description = "Get current weather for a city"
    parameters = {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "City name"}
        },
        "required": ["city"],
    }

    async def execute(self, args, ctx):
        city = args["city"]
        # Call your weather API here
        return tool_result(f"Weather in {city}: Sunny, 22°C")
```

## Running

```bash
cd examples/custom-tool
# Register your tool in the startup script
python run.py
```
