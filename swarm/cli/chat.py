"""Interactive chat REPL using Rich + prompt_toolkit."""

from __future__ import annotations

import asyncio
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from swarm.agent.loop import AgentLoop
from swarm.bus.queue import MessageBus
from swarm.providers.base import LLMProvider
from swarm.session.manager import SessionManager
from swarm.tools.registry import ToolRegistry
from swarm.tools.discovery import load_all_tools


class InteractiveChat:
    """Interactive chat interface for Swarm."""

    def __init__(self, provider: LLMProvider, session_name: str = "default",
                 config=None):
        self.provider = provider
        self.session_name = session_name
        self.config = config
        self.console = Console()
        self.bus = MessageBus()
        self.sessions = SessionManager(Path.home() / ".swarm")
        self.tools = ToolRegistry()
        load_all_tools(self.tools)
        self.loop = AgentLoop(
            bus=self.bus, provider=provider,
            workspace=Path.home() / ".swarm",
            sessions=self.sessions, tools=self.tools,
        )

    async def run(self) -> None:
        from swarm import __logo__
        self.console.print(__logo__, style="bold yellow")
        self.console.print(f"Swarm Chat — session: {self.session_name}")
        self.console.print("Type /help for commands, /exit to quit\n")

        history_path = Path.home() / ".swarm" / "chat_history"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        session = PromptSession(history=FileHistory(str(history_path)))
        session_key = f"cli:{self.session_name}"

        while True:
            try:
                with patch_stdout():
                    user_input = await session.prompt_async("you > ")
            except (EOFError, KeyboardInterrupt):
                self.console.print("\nGoodbye!")
                break

            user_input = user_input.strip()
            if not user_input:
                continue
            if user_input.lower() in ("/exit", "/quit"):
                self.console.print("Goodbye!")
                break

            self.console.print("[dim]thinking...[/dim]", end="\r")
            try:
                result = await self.loop.process_direct(user_input, session_key=session_key)
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")
                continue

            self.console.print(" " * 30, end="\r")
            if result and result.content:
                self.console.print(Panel(
                    Markdown(result.content), title="Swarm",
                    border_style="yellow",
                ))
