"""General-purpose utility functions."""

from __future__ import annotations

import re


def safe_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'_+', '_', name)
    name = name.strip('. ')
    return name or "unnamed"
