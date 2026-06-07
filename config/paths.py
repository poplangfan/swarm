"""XDG-compatible path resolution for Swarm data directories.

These functions provide sensible defaults (~/.swarm for config, ./data for runtime).
For production deployments, use optional overrides to point to configured paths.
"""

from pathlib import Path

# Global overrides — set once at startup from SwarmConfig if available
_override_data_dir: str | None = None
_override_log_dir: str | None = None
_override_chroma_dir: str | None = None


def set_overrides(
    data: str | None = None, logs: str | None = None, chroma: str | None = None
) -> None:
    """Set global path overrides from configuration. Call once at startup."""
    global _override_data_dir, _override_log_dir, _override_chroma_dir
    if data is not None:
        _override_data_dir = data
    if logs is not None:
        _override_log_dir = logs
    if chroma is not None:
        _override_chroma_dir = chroma


def config_dir() -> Path:
    """Return the user config directory (~/.swarm)."""
    path = Path.home() / ".swarm"
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    """Return the data directory (override or ./data)."""
    path = Path(_override_data_dir) if _override_data_dir else Path.cwd() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    """Return the log directory (override or data_dir/logs)."""
    if _override_log_dir:
        path = Path(_override_log_dir)
    else:
        path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def chroma_dir() -> Path:
    """Return the ChromaDB persistence directory (override or data_dir/chroma)."""
    if _override_chroma_dir:
        path = Path(_override_chroma_dir)
    else:
        path = data_dir() / "chroma"
    path.mkdir(parents=True, exist_ok=True)
    return path
