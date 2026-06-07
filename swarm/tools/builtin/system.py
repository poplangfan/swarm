"""System tools: /help, /status commands via tool."""

from swarm.agent.context import RequestContext
from swarm.tools.base import ToolBase, tool_result


class SystemTool(ToolBase):
    name = "system_command"
    description = "Execute built-in system commands like help or status"
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": ["help", "status"],
                "description": "The system command to execute",
            }
        },
        "required": ["command"],
    }

    def __init__(self, agent_loop=None):
        self._loop = agent_loop

    async def execute(self, args: dict, ctx: RequestContext) -> str:
        cmd = args.get("command", "help")
        if cmd == "help":
            return tool_result("Available commands: /help, /status, /clear")
        elif cmd == "status":
            return tool_result(f"Session: {ctx.chat_id}, Type: {ctx.chat_type}")
        return tool_result(f"Unknown: {cmd}")
