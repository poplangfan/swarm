"""System tools: /help, /status commands via tool."""

from agent.context import RequestContext
from tools.base import ToolBase, tool_result_json


class SystemTool(ToolBase):
    name = "system_command"
    description = "Execute built-in system commands like help or status"
    toolset = "core"
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
            return tool_result_json(result="Available commands: /help, /status, /clear")
        elif cmd == "status":
            return tool_result_json(
                result=f"Session: {ctx.chat_id}",
                chat_type=ctx.chat_type,
                user_id=ctx.user_id[:8] + "..." if ctx.user_id else "unknown",
            )
        return tool_result_json(error=f"Unknown command: {cmd}")
