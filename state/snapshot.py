"""State snapshot — save and restore full runtime state for crash recovery."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class StateSnapshot:
    """Creates and restores snapshots of runtime state.

    Snapshots include:
    - Session metadata (not full history — that's in SessionManager)
    - Active cron jobs
    - Token expiration timestamps
    - Plugin states
    """

    def __init__(self, storage_dir: Path):
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "snapshot.json"

    def save(self, state: dict[str, Any]) -> bool:
        """Save a state snapshot atomically."""
        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": 1,
            "data": state,
        }
        tmp_path = self._path.with_suffix(".tmp")
        try:
            tmp_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
            tmp_path.rename(self._path)
            logger.info("snapshot_saved", path=str(self._path))
            return True
        except Exception as e:
            logger.error("snapshot_save_failed", error=str(e))
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            return False

    def load(self) -> dict[str, Any] | None:
        """Load the most recent snapshot. Returns None if no snapshot exists."""
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text())
            logger.info("snapshot_loaded", timestamp=data.get("timestamp"))
            return data.get("data", {})
        except Exception as e:
            logger.error("snapshot_load_failed", error=str(e))
            return None

    def delete(self) -> None:
        """Delete the snapshot file."""
        if self._path.exists():
            self._path.unlink()
