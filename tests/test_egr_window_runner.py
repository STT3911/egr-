import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

from scripts import sync_egr_window as runner


def args(**overrides):
    return SimpleNamespace(**(dict(date_from=date(2026, 9, 8), date_to=date(2026, 9, 25),
        database="egr_db", max_companies=500, max_seconds=1200, total_seconds=3600,
        max_batches=4, backlog=True) | overrides))


def test_catchup_continues_old_target_then_new_window(monkeypatch):
    sync = AsyncMock(side_effect=[{"status": "pending"},
        {"status": "complete", "target": "2026-09-21"},
        {"status": "complete", "target": "2026-09-25"}])
    monkeypatch.setattr(runner, "sync_window", sync)
    monkeypatch.setattr(runner.asyncio, "sleep", AsyncMock())
    assert asyncio.run(runner.run_batches(args())) == 0
    assert sync.await_count == 3
    assert all(c.kwargs["backlog"] for c in sync.await_args_list)


def test_conflict_and_budget_are_not_success(monkeypatch):
    sync = AsyncMock(return_value={"status": "blocked", "unresolved": 1})
    monkeypatch.setattr(runner, "sync_window", sync)
    monkeypatch.setattr(runner.asyncio, "sleep", AsyncMock())
    assert asyncio.run(runner.run_batches(args())) == 3
    assert sync.await_count == 1
    sync.return_value = {"status": "pending"}
    assert asyncio.run(runner.run_batches(args(max_batches=1))) == 4


def test_catchup_waits_when_daily_job_holds_shared_lock(monkeypatch):
    sync = AsyncMock(side_effect=[{"status": "already_running"}, {"status": "up_to_date"}])
    sleep = AsyncMock()
    monkeypatch.setattr(runner, "sync_window", sync)
    monkeypatch.setattr(runner.asyncio, "sleep", sleep)
    assert asyncio.run(runner.run_batches(args())) == 0
    assert sleep.await_args.args == (30,)
