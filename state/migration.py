"""State migration — versioned schema/data migration between framework versions."""

from __future__ import annotations

from typing import Callable

import structlog

logger = structlog.get_logger(__name__)


class StateMigrator:
    """Handles state migration between framework versions.

    Each migration has a target version number and an `apply` function.
    Migrations are applied in order until the current code version is reached.
    """

    # NOTE: StateMigrator is reserved for future schema migration support.
    # It is fully implemented but not yet wired into the save/load pipeline.
    CURRENT_VERSION = 1

    def __init__(self):
        self._migrations: dict[int, Callable] = {}

    def register(self, version: int, migrate_fn: Callable) -> None:
        """Register a migration function for a specific version."""
        self._migrations[version] = migrate_fn

    def migrate(self, state: dict, from_version: int) -> dict:
        """Apply all pending migrations to bring state to CURRENT_VERSION."""
        current = dict(state)
        for version in range(from_version + 1, self.CURRENT_VERSION + 1):
            if version in self._migrations:
                try:
                    current = self._migrations[version](current)
                    logger.info("migration_applied", version=version)
                except Exception as e:
                    logger.error("migration_failed", version=version, error=str(e))
                    raise
        return current

    def needs_migration(self, state_version: int) -> bool:
        """Check if state needs migration."""
        return state_version < self.CURRENT_VERSION
