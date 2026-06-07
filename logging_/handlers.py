"""Log handlers: timed rotation + gzip compression + cleanup."""

from __future__ import annotations

import gzip
import shutil
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


class CompressingTimedRotatingFileHandler(TimedRotatingFileHandler):
    """TimedRotatingFileHandler that gzips rotated log files.

    Accepts an optional `log_name` prefix to identify this handler's files
    and prevent cross-handler glob collisions when multiple instances share
    the same log directory.
    """

    def __init__(
        self,
        log_dir: str,
        retention_days: int = 30,
        when: str = "midnight",
        interval: int = 1,
        backup_count: int = 30,
        encoding: str = "utf-8",
        log_name: str = "swarm",
    ):
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._retention_days = retention_days
        self._log_name = log_name

        filename = str(self._log_dir / f"{log_name}.log")
        super().__init__(
            filename=filename,
            when=when,
            interval=interval,
            backupCount=backup_count,
            encoding=encoding,
        )
        self.suffix = "%Y-%m-%d"

    def rotation_filename(self, default_name: str) -> str:
        # default_name is like "/path/swarm.log.2026-06-07" or
        # "/path/swarm-error.log.2026-06-07".
        # Extract the date suffix that TimedRotatingFileHandler computed.
        # The format is: baseFilename + "." + time.strftime(self.suffix)
        date_str = default_name.rsplit(".", 1)[-1]
        return str(self._log_dir / f"{self._log_name}-{date_str}.log")

    def rotate(self, source: str, dest: str) -> None:
        super().rotate(source, dest)
        # Only compress files matching THIS handler's prefix — avoids
        # cross-handler race conditions when multiple instances share log_dir.
        prefix = f"{self._log_name}-*.log"
        for f in self._log_dir.glob(prefix):
            if f.name == Path(source).name:
                continue
            gz_path = f.with_suffix(f.suffix + ".gz")
            if not gz_path.exists() and f.exists():
                try:
                    with open(f, "rb") as f_in:
                        with gzip.open(str(gz_path), "wb") as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    f.unlink()
                except FileNotFoundError:
                    pass  # File was already removed by another process
        self._cleanup_old_logs()

    def _cleanup_old_logs(self) -> None:
        cutoff = time.time() - (self._retention_days * 86400)
        for pattern in [f"{self._log_name}-*.log.gz", f"{self._log_name}-*.log"]:
            for f in self._log_dir.glob(pattern):
                if f.stat().st_mtime < cutoff:
                    try:
                        f.unlink()
                    except FileNotFoundError:
                        pass
