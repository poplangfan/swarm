"""Tests for cron scheduler, store, and parser."""

import pytest
import time
from pathlib import Path
from cron.scheduler import CronScheduler
from cron.store import CronStore
from cron.parser import CronParser


class TestCronParser:
    @pytest.mark.asyncio
    async def test_every_day_at_time(self):
        parser = CronParser()
        result = await parser.parse("every day at 9am")
        assert "0 9" in result["cron"] or "Every day" in result["description"]

    @pytest.mark.asyncio
    async def test_every_n_minutes(self):
        parser = CronParser()
        result = await parser.parse("every 30 minutes")
        assert "30" in result["cron"] or "30" in result["description"]

    @pytest.mark.asyncio
    async def test_every_weekday(self):
        parser = CronParser()
        result = await parser.parse("every weekday at 2pm")
        assert result["confidence"] > 0

    @pytest.mark.asyncio
    async def test_every_monday(self):
        parser = CronParser()
        result = await parser.parse("every monday at 10am")
        assert result["confidence"] > 0

    @pytest.mark.asyncio
    async def test_fallback_default(self):
        parser = CronParser()
        result = await parser.parse("some gibberish that makes no sense")
        # Should return a default with low confidence
        assert "confidence" in result
        assert result["confidence"] < 0.6

    @pytest.mark.asyncio
    async def test_pm_conversion(self):
        """PM times should be converted to 24h."""
        parser = CronParser()
        result = await parser.parse("every day at 2pm")
        # "0 2 * * *" would be 2am — wrong
        # "0 14 * * *" is correct (2pm)
        cron = result["cron"]
        parts = cron.strip().split()
        assert parts[1] == "14", f"Expected 14 for 2pm, got {parts[1]}"

    @pytest.mark.asyncio
    async def test_pm_weekly(self):
        """weekly at 5pm should give hour=17."""
        parser = CronParser()
        result = await parser.parse("weekly at 5pm")
        cron = result["cron"]
        parts = cron.strip().split()
        assert parts[1] == "17", f"Expected 17 for 5pm, got {parts[1]}"

    def test_calculate_next_run_daily(self):
        parser = CronParser()
        next_run = parser.calculate_next_run("0 9 * * *")
        assert next_run is not None
        assert "T" in next_run  # ISO format

    def test_calculate_next_run_every_n_minutes(self):
        parser = CronParser()
        next_run = parser.calculate_next_run("*/30 * * * *")
        assert next_run is not None

    def test_invalid_cron_returns_none(self):
        parser = CronParser()
        assert parser.calculate_next_run("invalid") is None

    def test_describe_cron_daily(self):
        parser = CronParser()
        desc = parser._describe_cron("0 9 * * *")
        assert "9:00" in desc or "every" in desc.lower()

    def test_describe_cron_weekday(self):
        parser = CronParser()
        desc = parser._describe_cron("0 14 * * 1-5")
        assert "weekday" in desc.lower() or "14" in desc


class TestCronStore:
    def test_save_and_load(self, temp_dir):
        store = CronStore(temp_dir)
        store.save("job_1", "reminder", {"text": "standup", "minutes": 30})
        jobs = store.load_all()
        assert len(jobs) == 1
        assert jobs[0]["job_id"] == "job_1"
        assert jobs[0]["config"]["text"] == "standup"

    def test_delete(self, temp_dir):
        store = CronStore(temp_dir)
        store.save("job_1", "reminder", {"text": "test"})
        store.delete("job_1")
        assert len(store.load_all()) == 0

    def test_disable(self, temp_dir):
        store = CronStore(temp_dir)
        store.save("job_1", "reminder", {"text": "test"})
        store.disable("job_1")
        # Disabled jobs not loaded
        assert len(store.load_all()) == 0

    def test_multiple_jobs(self, temp_dir):
        store = CronStore(temp_dir)
        for i in range(10):
            store.save(f"job_{i}", "reminder", {"n": i})
        assert len(store.load_all()) == 10

    def test_update_last_run(self, temp_dir):
        store = CronStore(temp_dir)
        store.save("job_1", "reminder", {"text": "test"})
        store.update_last_run("job_1")
        jobs = store.load_all()
        assert len(jobs) == 1


class TestCronScheduler:
    def test_add_and_list_jobs(self):
        s = CronScheduler()
        counter = 0

        def inc():
            nonlocal counter
            counter += 1

        s.add_interval_job("test_job", inc, minutes=60)
        jobs = s.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "test_job"

    def test_remove_job(self):
        s = CronScheduler()
        s.add_interval_job("test_job", lambda: None, minutes=60)
        assert s.remove_job("test_job")
        assert len(s.list_jobs()) == 0

    def test_remove_nonexistent(self):
        s = CronScheduler()
        assert not s.remove_job("nope")

    def test_get_job_count(self):
        s = CronScheduler()
        s.add_interval_job("a", lambda: None, minutes=10)
        s.add_interval_job("b", lambda: None, minutes=20)
        assert s.get_job_count() == 2

    def test_add_cron_job(self):
        s = CronScheduler()
        s.add_cron_job("daily_job", lambda: None, "0 9 * * *")
        assert s.get_job_count() == 1

    def test_invalid_cron_fails(self):
        s = CronScheduler()
        with pytest.raises(ValueError):
            s.add_cron_job("bad", lambda: None, "invalid")

    def test_replace_existing(self):
        s = CronScheduler()
        s.add_interval_job("only", lambda: None, minutes=10)
        s.add_interval_job("only", lambda: None, minutes=20)
        assert s.get_job_count() == 1
