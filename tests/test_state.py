"""Tests for state management — persistent store, snapshots, migration."""

import json
import pytest
from pathlib import Path
from swarm.state.store import StateStore
from swarm.state.snapshot import StateSnapshot
from swarm.state.migration import StateMigrator


class TestStateStore:
    @pytest.mark.asyncio
    async def test_set_and_get(self, temp_dir):
        store = StateStore(temp_dir)
        await store.set("app_ticket", "ticket_xyz")
        assert await store.get("app_ticket") == "ticket_xyz"

    @pytest.mark.asyncio
    async def test_get_default(self, temp_dir):
        store = StateStore(temp_dir)
        assert await store.get("nonexistent", "default") == "default"
        assert await store.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_delete(self, temp_dir):
        store = StateStore(temp_dir)
        await store.set("key1", "val1")
        await store.delete("key1")
        assert await store.get("key1") is None

    @pytest.mark.asyncio
    async def test_exists(self, temp_dir):
        store = StateStore(temp_dir)
        await store.set("exists", True)
        assert await store.exists("exists")
        assert not await store.exists("no")

    @pytest.mark.asyncio
    async def test_keys(self, temp_dir):
        store = StateStore(temp_dir)
        await store.set("a", 1)
        await store.set("b", 2)
        await store.set("c", 3)
        keys = await store.keys()
        assert len(keys) == 3
        assert "a" in keys

    @pytest.mark.asyncio
    async def test_get_all(self, temp_dir):
        store = StateStore(temp_dir)
        await store.set("x", [1, 2, 3])
        await store.set("y", {"key": "value"})
        all_data = await store.get_all()
        assert all_data["x"] == [1, 2, 3]
        assert all_data["y"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_persistence(self, temp_dir):
        store = StateStore(temp_dir)
        await store.set("persist", "survive_restart")
        # New store pointing at same dir
        store2 = StateStore(temp_dir)
        assert await store2.get("persist") == "survive_restart"

    @pytest.mark.asyncio
    async def test_complex_types(self, temp_dir):
        store = StateStore(temp_dir)
        data = {"nested": {"list": [1, 2, 3], "string": "hello"}}
        await store.set("complex", data)
        assert await store.get("complex") == data


class TestStateSnapshot:
    def test_save_and_load(self, temp_dir):
        snap = StateSnapshot(temp_dir)
        state = {"version": 1, "sessions": ["a", "b", "c"], "cursor": 42}
        assert snap.save(state)
        loaded = snap.load()
        assert loaded == state

    def test_load_nonexistent(self, temp_dir):
        snap = StateSnapshot(temp_dir)
        assert snap.load() is None

    def test_delete(self, temp_dir):
        snap = StateSnapshot(temp_dir)
        snap.save({"test": True})
        snap.delete()
        assert snap.load() is None

    def test_overwrite(self, temp_dir):
        snap = StateSnapshot(temp_dir)
        snap.save({"version": 1})
        snap.save({"version": 2})
        assert snap.load()["version"] == 2


class TestStateMigrator:
    def test_no_migration_needed(self):
        migrator = StateMigrator()
        assert not migrator.needs_migration(StateMigrator.CURRENT_VERSION)

    def test_migration_needed(self):
        migrator = StateMigrator()
        assert migrator.needs_migration(0)

    def test_apply_registered_migration(self):
        migrator = StateMigrator()
        migrator.register(1, lambda s: {**s, "migrated": True})
        result = migrator.migrate({"original": True}, from_version=0)
        assert result["original"] is True
        assert result.get("migrated") is True

    def test_migration_error_propagates(self):
        migrator = StateMigrator()
        migrator.register(1, lambda s: (_ for _ in ()).throw(RuntimeError("fail")))
        with pytest.raises(RuntimeError):
            migrator.migrate({}, from_version=0)

    def test_multiple_migrations_applied_in_order(self):
        migrator = StateMigrator()
        migrator.register(1, lambda s: {**s, "v1": True})
        migrator.register(2, lambda s: {**s, "v2": True})
        # CURRENT_VERSION should be >= 2 for this to work
        # Override for testing
        migrator.CURRENT_VERSION = 2
        result = migrator.migrate({"base": True}, from_version=0)
        assert result["v1"] is True
        assert result["v2"] is True
