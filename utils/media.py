"""Media (image/audio) format helpers."""

from __future__ import annotations

import mimetypes
from pathlib import Path


def detect_image_mime(data: bytes) -> str | None:
    """Detect image MIME type from magic bytes."""
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def guess_mime_type(path: str | Path) -> str:
    """Guess MIME type from file extension."""
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"
