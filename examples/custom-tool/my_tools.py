"""Example custom tool for Swarm."""

from tools.base import ToolBase, tool_result
from agent.context import RequestContext


class WeatherTool(ToolBase):
    """Get current weather information for a city."""

    name = "get_weather"
    description = "Get current weather conditions for a specified city"
    parameters = {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "City name (e.g., 'Beijing', 'Shanghai')",
            },
        },
        "required": ["city"],
    }

    async def execute(self, args: dict, ctx: RequestContext) -> str:
        city = args.get("city", "Unknown")
        # In production, call a real weather API here
        # For demo, return mock data
        weather_data = {
            "Beijing": "Partly cloudy, 15°C, wind NE 3m/s",
            "Shanghai": "Light rain, 18°C, wind SE 5m/s",
            "Shenzhen": "Sunny, 28°C, wind SW 2m/s",
            "Hangzhou": "Cloudy, 20°C, wind N 4m/s",
        }
        info = weather_data.get(city, f"Sunny, 22°C (mock data for {city})")
        return tool_result(f"Weather for {city}", conditions=info)


class CalculatorTool(ToolBase):
    """Simple calculator for arithmetic operations."""

    name = "calculator"
    description = "Perform basic arithmetic calculations"
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Arithmetic expression (e.g., '2 + 3 * 4')",
            },
        },
        "required": ["expression"],
    }

    async def execute(self, args: dict, ctx: RequestContext) -> str:
        expr = args.get("expression", "0")
        try:
            # WARNING: eval is used here for demo purposes.
            # In production, use a proper expression parser.
            result = eval(expr, {"__builtins__": {}}, {})
            return tool_result(f"Result: {expr} = {result}")
        except Exception as e:
            return tool_result(f"Error calculating '{expr}': {e}")
