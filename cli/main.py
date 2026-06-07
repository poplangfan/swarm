"""CLI entry point — swarm chat / swarm ws / swarm init."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console

__version__ = "0.1.3"
__logo__ = r"""
   _____
  / ___/      __  ______ ___  ____ ___  ___
  \__ \| | /| / / / __ `__ \/ __ `__ \/ _ \
 ___/ /| |/ |/ / / / / / / / / / / / /  __/
/____/ |__/|__/ /_/ /_/ /_/_/ /_/ /_/\___/
"""

app = typer.Typer(name="swarm", help="Swarm — Feishu AI Agent Framework")
console = Console()


@app.command()
def version() -> None:
    """Print version and exit."""
    console.print(__logo__, style="bold yellow")
    console.print(f"Swarm v{__version__}", style="green")


@app.command()
def chat(
    session: str = typer.Option("default", "--session", "-s"),
    config_path: str = typer.Option("config.yaml", "--config", "-c"),
) -> None:
    """Start interactive chat mode."""
    from config.loader import load_config
    from providers.factory import make_provider

    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("Run 'swarm init' to create a config")
        raise typer.Exit(1)

    provider = make_provider(config.llm)
    from cli.chat import InteractiveChat

    chat_app = InteractiveChat(provider=provider, session_name=session, config=config)
    asyncio.run(chat_app.run())


@app.command()
def ws(
    config_path: str = typer.Option("config.yaml", "--config", "-c"),
) -> None:
    """Start Feishu WebSocket mode."""
    from agent.loop import AgentLoop
    from bus.queue import MessageBus
    from config.loader import load_config
    from gateway.feishu_ws import FeishuWebSocket
    from logging_.setup import setup_logging
    from memory.store import ChromaMemoryStore
    from providers.factory import make_provider
    from session.manager import SessionManager
    from tools.discovery import load_all_tools
    from tools.registry import ToolRegistry

    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    setup_logging(
        level=config.logging.level,
        json_format=config.logging.json_format,
        log_dir=str(Path(config.logging.log_dir).expanduser()),
        retention_days=config.logging.retention_days,
        compress=config.logging.compress,
        audit_enabled=config.logging.audit_enabled,
        error_separate=config.logging.error_separate,
    )

    bus = MessageBus()
    provider = make_provider(config.llm)
    data_dir = Path.home() / ".swarm"

    tools = ToolRegistry()
    count = load_all_tools(tools)
    console.print(f"[dim]Loaded {count} tools[/dim]")

    sessions = SessionManager(data_dir)
    memory = ChromaMemoryStore(Path(config.memory.chroma_path).expanduser())

    loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=data_dir,
        tools=tools,
        sessions=sessions,
        memory=memory,
    )

    feishu = FeishuWebSocket(
        app_id=config.feishu.app_id,
        app_secret=config.feishu.app_secret,
        bus=bus,
        domain=config.feishu.domain,
        group_policy=config.feishu.group_policy,
    )

    async def run_all():
        import signal

        loop_task = asyncio.create_task(loop.run())
        ws_task = asyncio.create_task(feishu.start())
        stop_event = asyncio.Event()

        def _signal_handler():
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            asyncio.get_running_loop().add_signal_handler(sig, _signal_handler)

        # Wait for stop signal or task failure
        done, pending = await asyncio.wait(
            [loop_task, ws_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        # Check for task exceptions
        for task in done:
            try:
                task.result()
            except Exception as e:
                console.print(f"[red]Task crashed: {e}[/red]")

        if not stop_event.is_set():
            stop_event.set()

        console.print("[yellow]Shutting down...[/yellow]")
        await loop.shutdown(timeout=10.0)
        await feishu.stop()
        for task in [loop_task, ws_task]:
            if not task.done():
                task.cancel()

    try:
        asyncio.run(run_all())
    except KeyboardInterrupt:
        pass


@app.command()
def init() -> None:
    """Interactive configuration wizard."""
    console.print(__logo__, style="bold yellow")
    console.print("Swarm Initialization Wizard\n")
    swarm_home = Path.home() / ".swarm"
    swarm_home.mkdir(parents=True, exist_ok=True)
    # Create standard subdirectories
    for subdir in ["chroma", "logs", "skills"]:
        (swarm_home / subdir).mkdir(parents=True, exist_ok=True)
    config_path = swarm_home / "config.yaml"
    if config_path.exists():
        overwrite = typer.confirm(f"{config_path} already exists. Overwrite?")
        if not overwrite:
            console.print("[yellow]Aborted.[/yellow]")
            return
    example = """# Swarm configuration
llm:
  provider: "anthropic"
  base_url: "https://api.deepseek.com/anthropic"
  api_key: "sk-your-key"
  model: "deepseek-v4-pro"

feishu:
  app_id: "cli_xxx"
  app_secret: "xxx"

logging:
  level: "INFO"
  json_format: true
  log_dir: "~/.swarm/logs"
"""
    config_path.write_text(example)
    console.print(f"[green]Created {config_path}[/green]")
    console.print(
        "\nNext: edit config.yaml with your credentials, then run [bold]swarm chat[/bold]"
    )


@app.command()
def validate(
    config_path: str = typer.Option("config.yaml", "--config", "-c"),
) -> None:
    """Validate a configuration file."""
    from config.loader import load_config

    try:
        config = load_config(config_path)
        console.print("[green]Config valid[/green]")
        console.print(f"  Provider: {config.llm.provider}")
        console.print(f"  Model: {config.llm.model}")
        console.print(f"  Feishu App: {config.feishu.app_id}")
    except Exception as e:
        console.print(f"[red]Validation failed: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
