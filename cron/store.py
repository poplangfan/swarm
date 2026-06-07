"""Cron job persistence — SQLite store for surviving restarts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class CronStore:
    """SQLite-backed persistent cron job store."""

    def __init__(self, data_dir: Path):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "cron_jobs.db"
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cron_jobs (
                    job_id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_run TEXT,
                    enabled INTEGER DEFAULT 1
                )
            """)
            conn.commit()

    def save(self, job_id: str, job_type: str, config: dict[str, Any]) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cron_jobs (job_id, job_type, config_json, created_at) VALUES (?, ?, ?, datetime('now'))",
                (job_id, job_type, json.dumps(config)),
            )
            conn.commit()

    def load_all(self) -> list[dict[str, Any]]:
        with sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                "SELECT job_id, job_type, config_json, enabled FROM cron_jobs WHERE enabled=1"
            ).fetchall()
        return [
            {"job_id": r[0], "job_type": r[1], "config": json.loads(r[2]), "enabled": bool(r[3])}
            for r in rows
        ]

    def delete(self, job_id: str) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("DELETE FROM cron_jobs WHERE job_id=?", (job_id,))
            conn.commit()

    def update_last_run(self, job_id: str) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                "UPDATE cron_jobs SET last_run=datetime('now') WHERE job_id=?",
                (job_id,),
            )
            conn.commit()

    def disable(self, job_id: str) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("UPDATE cron_jobs SET enabled=0 WHERE job_id=?", (job_id,))
            conn.commit()
