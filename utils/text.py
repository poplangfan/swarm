"""Text manipulation utilities."""

from __future__ import annotations

from datetime import datetime


def truncate_text(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, adding ellipsis if truncated."""
    if len(text) <= max_chars:
        return text
    head = text[: max_chars // 2]
    tail = text[-(max_chars // 2) :]
    return f"{head}\n... [truncated {len(text) - max_chars:,} chars] ...\n{tail}"


def current_time_str(tz_name: str | None = None) -> str:
    """Return current time as formatted string."""
    if tz_name:
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(tz_name)
        except Exception:
            tz = None
    else:
        tz = None
    return datetime.now(tz=tz).strftime("%Y-%m-%d %H:%M:%S %Z")
