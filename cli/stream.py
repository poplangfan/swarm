"""Terminal streaming renderer for real-time LLM output.

NOTE: reserved for future CLI streaming integration.
"""

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown


class StreamRenderer:
    """Renders streaming LLM output in the terminal using Rich Live."""

    def __init__(self):
        self.console = Console()
        self._buffer = ""
        self._live: Live | None = None

    def __enter__(self):
        self._live = Live("", console=self.console, refresh_per_second=10)
        return self

    def __exit__(self, *args):
        if self._live:
            self._live.stop()

    def add(self, delta: str) -> None:
        self._buffer += delta
        if self._live:
            self._live.update(Markdown(self._buffer))

    def finalize(self) -> str:
        if self._live:
            self._live.stop()
        return self._buffer
