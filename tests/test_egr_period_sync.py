import asyncio
from datetime import date
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import SystemState
from app.services.egr_client import EGRClient
from app.services.egr_period_sync import (
    PERIOD_SOURCES, PeriodSyncStore, collect_day, run_period_sync, validate_period_rows,
)

DAY = date(2026, 9, 17)


@pytest.fixture
def store():
    engine = create_engine("sqlite://")
    SystemState.__table__.create(engine)
    with Session(engine) as db:
        yield PeriodSyncStore(db)
    engine.dispose()


def feed_client(rows=None):
    client = Mock()
    rows = rows or {}
    client.get_period_rows = AsyncMock(side_effect=lambda source, day: rows.get(source, []))
    return client


def run(store, client, refresh, **kwargs):
    opts = dict(target=DAY, bootstrap_days=1, delay=0)
    opts.update(kwargs)
    return asyncio.run(run_period_sync(store, client, refresh, **opts))


def test_all_eight_sources_union_and_both_ip_to_jur_unps():
    payloads = {source: [{"ngrn": 193879557}] for source in PERIOD_SOURCES}
    payloads["getIPtoJurByPeriod"] = [{"ipngrn": 300325070, "ulngrn": 193879557}]
    client = feed_client(payloads)
    result = asyncio.run(collect_day(client, DAY, delay=0))
    assert result["unps"] == [193879557, 300325070]
    assert len(client.get_period_rows.await_args_list) == 8
    assert set(result["counts"]) == set(PERIOD_SOURCES)
    assert result["events"] == {"193879557": [{"ngrn": 193879557}]}


@pytest.mark.parametrize("rows", [None, {}, {"error": "unavailable"}, [None], [{}], [{"ngrn": True}],
                                  [{"ngrn": 1.1}], [{"ngrn": 0}], [{"ngrn": "bad"}]])
def test_invalid_feed_never_means_no_changes(rows):
    with pytest.raises(ValueError):
        validate_period_rows("getAddressByPeriod", rows)


def test_transition_requires_both_identifiers():
    with pytest.raises(ValueError):
        validate_period_rows("getIPtoJurByPeriod", [{"ipngrn": 300325070}])


@pytest.mark.parametrize("status,body", [(500, '[]'), (404, ''), (302, ''), (200, ''), (200, '{}')])
def test_strict_http_errors_are_not_empty_lists(status, body):
    async def check():
        client = EGRClient()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(status, text=body)))
        try:
            with pytest.raises((httpx.HTTPStatusError, ValueError)):
                await client.get_period_rows("getAddressByPeriod", "17.09.2026")
        finally:
            await client.close()
    asyncio.run(check())


@pytest.mark.parametrize("status,body", [(200, '[]'), (204, '')])
def test_strict_valid_empty_response(status, body):
    async def check():
        client = EGRClient()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(status, text=body)))
        try:
            assert await client.get_period_rows("getAddressByPeriod", "17.09.2026") == []
        finally:
            await client.close()
    asyncio.run(check())


def test_feed_failure_keeps_cursor_and_does_not_start_refresh(store):
    client = feed_client()
    async def fetch(source, day):
        if source == "getAddressByPeriod":
            raise RuntimeError("source unavailable")
        return [{"ngrn": 193879557}]
    client.get_period_rows.side_effect = fetch
    refresh = AsyncMock()
    with pytest.raises(RuntimeError):
        run(store, client, refresh)
    assert store.load()["next_day"] == DAY.isoformat()
    assert store.load()["pending"] is None
    assert store.db.get(SystemState, "egr_last_sync_date") is None
    refresh.assert_not_called()


def test_suspected_truncation_stops_before_any_acknowledgement(store):
    client = feed_client({"getAddressByPeriod": [{"ngrn": 193879557}] * 2})
    with pytest.raises(ValueError, match="possible truncation"):
        run(store, client, AsyncMock(), row_limit=2)
    assert store.load()["pending"] is None


def test_failure_resumes_failed_unp_without_refetching_completed_feeds(store):
    client = feed_client({"getAddressByPeriod": [{"ngrn": 193879557}, {"ngrn": 300325070}]})
    refresh = AsyncMock(side_effect=[None, RuntimeError("failed card")])
    with pytest.raises(RuntimeError):
        run(store, client, refresh)
    assert store.load()["pending"]["next_index"] == 1
    assert store.db.get(SystemState, "egr_last_sync_date") is None
    refresh2 = AsyncMock()
    result = run(store, client, refresh2)
    assert result["status"] == "complete"
    refresh2.assert_awaited_once_with(300325070)
    assert client.get_period_rows.await_count == 8
    assert store.db.get(SystemState, "egr_last_sync_date").value == DAY.isoformat()
    assert run(store, client, refresh2)["status"] == "up_to_date"
    assert client.get_period_rows.await_count == 8


def test_batch_limit_has_durable_continuation(store):
    client = feed_client({"getAddressByPeriod": [{"ngrn": 193879557}, {"ngrn": 300325070}]})
    refresh = AsyncMock()
    assert run(store, client, refresh, max_companies=1)["status"] == "pending"
    assert store.load()["pending"]["next_index"] == 1
    assert run(store, client, refresh, max_companies=1)["status"] == "complete"
    assert refresh.await_count == 2


def test_new_day_replays_overlap_not_entire_registry(store):
    client = feed_client()
    run(store, client, AsyncMock())
    client.get_period_rows.reset_mock()
    run(store, client, AsyncMock(), target=date(2026, 9, 18), overlap_days=3)
    days = [call.args[1] for call in client.get_period_rows.await_args_list]
    assert days == ["16.09.2026"] * 8 + ["17.09.2026"] * 8 + ["18.09.2026"] * 8


def test_old_monitoring_cursor_does_not_regress_during_bootstrap(store):
    store.db.add(SystemState(key="egr_last_sync_date", value="2026-09-17"))
    store.db.commit()
    client = feed_client()
    run(store, client, AsyncMock(), target=date(2026, 9, 16))
    assert store.db.get(SystemState, "egr_last_sync_date").value == "2026-09-17"


def test_event_and_checkpoint_commit_together(store, monkeypatch):
    import app.services.egr_period_sync as module
    event = {"ngrn": 193879557, "ngr04004": 18241482500}
    client = feed_client({"getEventByPeriod": [event]})
    emit = Mock(side_effect=RuntimeError("failed notification"))
    monkeypatch.setattr(module, "emit_egr_source_events", emit)
    with pytest.raises(RuntimeError):
        run(store, client, AsyncMock())
    assert store.load()["pending"]["next_index"] == 0
    emit.side_effect = None
    run(store, client, AsyncMock())
    assert emit.call_count == 2
    assert store.load()["completed_target"] == DAY.isoformat()


@pytest.mark.parametrize("failed_endpoint", ["getAllAddressByRegNum", "getAllVEDByRegNum", "getAllJurNamesByRegNum"])
def test_full_history_failure_never_returns_partial_snapshot(failed_endpoint):
    async def check():
        def respond(req):
            if failed_endpoint in req.url.path:
                return httpx.Response(503)
            if "getBaseInfoByRegNum" in req.url.path:
                return httpx.Response(200, json=[{"ngrn": 193879557, "nsi00211": {"nkvob": 1}}])
            return httpx.Response(200, json=[])
        client = EGRClient()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_full_company_history_strict(193879557, delay=0)
        finally:
            await client.close()
    asyncio.run(check())


@pytest.mark.parametrize("entity_type,names_endpoint", [(1, "getAllJurNamesByRegNum"), (2, "getAllIPFIOByRegNum")])
def test_strict_history_selects_correct_name_source(entity_type, names_endpoint):
    async def check():
        paths = []
        def respond(req):
            paths.append(req.url.path)
            if "getBaseInfoByRegNum" in req.url.path:
                return httpx.Response(200, json={"ngrn": 193879557, "nsi00211": {"nkvob": entity_type}})
            return httpx.Response(200, json=[])
        client = EGRClient()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            result = await client.get_full_company_history_strict(193879557, delay=0)
            assert len(paths) == 5
            assert paths[-2].endswith(names_endpoint + "/193879557")
            assert paths[-1].endswith("getEventByRegNum/193879557")
            assert set(result) == {"base_info", "addresses", "ved", "names", "events"}
        finally:
            await client.close()
    asyncio.run(check())


def test_strict_history_rejects_foreign_unp():
    async def check():
        client = EGRClient()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(
            200, json={"ngrn": 300325070, "nsi00211": {"nkvob": 1}},
        )))
        try:
            with pytest.raises(ValueError, match="Invalid EGR base"):
                await client.get_full_company_history_strict(193879557, delay=0)
        finally:
            await client.close()
    asyncio.run(check())


def test_task_uses_strict_fetch_processes_before_ack_and_closes_clients(monkeypatch):
    from unittest.mock import MagicMock
    import app.core.database as database
    import app.services.egr_period_sync as periods
    import app.tasks.sync_tasks as tasks

    connection = MagicMock()
    connection.execute.return_value.scalar.return_value = True
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = connection
    monkeypatch.setattr(database, "engine", engine)
    db = Mock()
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
    client = Mock(get_full_company_history_strict=AsyncMock(return_value={"base_info": {"ngrn": 193879557}}),
                  close=AsyncMock())
    monkeypatch.setattr(tasks, "EGRClient", lambda url: client)
    aggregator = Mock()
    aggregator.egr_client.close = AsyncMock()
    aggregator.mobile_client.close = AsyncMock()
    monkeypatch.setattr(tasks, "AggregatorService", lambda: aggregator)

    async def orchestrate(store, passed_client, refresh, **kwargs):
        assert passed_client is client
        await refresh(193879557)
        aggregator.save_raw_payload.assert_called_once()
        aggregator.process_raw_data.assert_called_once_with(
            193879557, raw_entry=aggregator.save_raw_payload.return_value, authoritative_addresses=True,
        )
        aggregator.redis.delete.assert_called_once_with("company_profile_v2:193879557")
        return {"status": "complete"}

    monkeypatch.setattr(periods, "run_period_sync", orchestrate)
    assert tasks.sync_daily_changes.run() == {"status": "complete"}
    client.close.assert_awaited_once()
    aggregator.egr_client.close.assert_awaited_once()
    aggregator.close.assert_called_once()
    db.close.assert_called_once()


def test_task_does_not_start_if_another_instance_holds_lock(monkeypatch):
    from unittest.mock import MagicMock
    import app.core.database as database
    import app.tasks.sync_tasks as tasks

    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value.execute.return_value.scalar.return_value = False
    monkeypatch.setattr(database, "engine", engine)
    create_client = Mock()
    monkeypatch.setattr(tasks, "EGRClient", create_client)
    assert tasks.sync_daily_changes.run() == {"status": "already_running"}
    create_client.assert_not_called()
