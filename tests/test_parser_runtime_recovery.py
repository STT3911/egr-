import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import requests

from app.services.egr_snapshot import export_snapshot


def test_snapshot_permission_failure_happens_before_network(tmp_path, monkeypatch):
    import app.services.egr_snapshot as module
    client = Mock(get_period_rows=AsyncMock())
    monkeypatch.setattr(module.tempfile, "mkstemp", Mock(side_effect=PermissionError("denied")))
    with pytest.raises(PermissionError):
        asyncio.run(export_snapshot(client, "01.01.2026", "01.01.2026", tmp_path, min_free_mb=0))
    client.get_period_rows.assert_not_called()


def test_low_disk_stops_before_requests(tmp_path, monkeypatch):
    import app.services.egr_snapshot as module
    monkeypatch.setattr(module.shutil, "disk_usage", lambda path: SimpleNamespace(free=1024))
    client = Mock(get_period_rows=AsyncMock())
    with pytest.raises(RuntimeError, match="disk"):
        asyncio.run(export_snapshot(client, "01.01.2026", "01.01.2026", tmp_path))
    client.get_period_rows.assert_not_called()


def test_failed_snapshot_preserves_complete_file(tmp_path):
    target = tmp_path / "01-01-2026_to_01-01-2026.json"
    target.write_text('[{"old": true}]')
    client = Mock(get_period_rows=AsyncMock(return_value=[{"ngrn": 193879557}]),
                  get_full_company_history_strict=AsyncMock(side_effect=RuntimeError("network")))
    with pytest.raises(RuntimeError):
        asyncio.run(export_snapshot(client, "01.01.2026", "01.01.2026", tmp_path, min_free_mb=0))
    assert json.loads(target.read_text()) == [{"old": True}]
    assert len(list(tmp_path.glob("*.partial"))) == 1


def test_snapshot_streams_bounded_batches(tmp_path, monkeypatch):
    import app.services.egr_snapshot as module
    active = 0
    maximum = 0
    original_sleep = asyncio.sleep
    async def no_delay(seconds):
        await original_sleep(0)
    monkeypatch.setattr(module.asyncio, "sleep", no_delay)
    async def fetch(unp):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await original_sleep(0)
        active -= 1
        return {"base_info": {"ngrn": unp}}
    client = Mock(get_period_rows=AsyncMock(return_value=[{"ngrn": 100000000 + i} for i in range(21)]),
                  get_full_company_history_strict=fetch)
    count = asyncio.run(export_snapshot(client, "01.01.2026", "01.01.2026", tmp_path, min_free_mb=0))
    assert count == 21 and maximum <= 4
    assert len(json.loads(next(tmp_path.glob("*.json")).read_text())) == 21


def test_gias_timeout_retries_without_resetting_history(monkeypatch):
    import app.tasks.sync_tasks as tasks
    from celery.exceptions import Retry
    db = Mock()
    service = Mock()
    service.sync_index.side_effect = requests.exceptions.ConnectionError("read timeout")
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(tasks, "GiasContractService", lambda db: service)
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(tasks.sync_gias_contract_index, "retry", retry)
    with pytest.raises(Retry):
        tasks.sync_gias_contract_index.run(full=True, max_pages=50)
    assert retry.call_args.kwargs["kwargs"] == {"full": False, "max_pages": 50}
    assert retry.call_args.kwargs["args"] == ()
    assert retry.call_args.kwargs["countdown"] == 300
    assert retry.call_args.kwargs["expires"] == 900
    db.rollback.assert_called_once()
    db.close.assert_called_once()
    service.close.assert_called_once()


def test_unsafe_full_history_schedule_is_opt_in():
    from app.tasks.celery_app import celery_app
    from app.core.config import settings
    if not settings.EGR_HISTORICAL_SCHEDULE_ENABLED:
        assert "auto-fetch-historical" not in celery_app.conf.beat_schedule


def test_old_json_schedule_is_opt_in():
    from app.tasks.celery_app import celery_app
    from app.core.config import settings
    if not settings.EGR_JSON_IMPORT_SCHEDULE_ENABLED:
        assert "load-from-json" not in celery_app.conf.beat_schedule
