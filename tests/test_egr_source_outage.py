"""Persistent outages: no false completion, no repeated alerts or refetch storm."""
import asyncio
import copy
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import SystemState
from app.services.egr_client import EGRClient
from app.services.egr_period_sync import PeriodSyncStore, PERIOD_SOURCES, run_period_sync

DAY = date(2026, 10, 7)


@pytest.fixture
def store():
    engine = create_engine('sqlite://')
    SystemState.__table__.create(engine)
    with Session(engine) as db:
        yield PeriodSyncStore(db)
    engine.dispose()


def execute(store, client, refresh, now):
    return asyncio.run(run_period_sync(store, client, refresh, target=DAY,
                                       bootstrap_days=1, delay=0, clock=lambda: now))


def test_period_reads_have_longer_timeout_than_company_reads():
    observed = []
    def respond(request):
        observed.append(request.extensions['timeout']['read'])
        return httpx.Response(200, json=[])
    async def check():
        client = EGRClient()
        client._client = httpx.AsyncClient(timeout=client._timeout, transport=httpx.MockTransport(respond))
        try:
            await client.get_period_rows('getEventByPeriod', '07.10.2026')
            await client._request_strict('getBaseInfoByRegNum/193879557')
        finally:
            await client.close()
    asyncio.run(check())
    assert observed == [120.0, 30.0]


def test_timeout_keeps_completed_feeds_and_silently_waits_across_restart(store):
    fail = [True]
    def fetch(source, day):
        if source == 'getEventByPeriod' and fail[0]:
            raise httpx.ReadTimeout('source down')
        return [{'ngrn': 193879557}] if source == 'getBaseInfoByPeriod' else []
    client = Mock(get_period_rows=AsyncMock(side_effect=fetch))
    refresh = AsyncMock()
    first = execute(store, client, refresh, 1000)
    assert first['status'] == 'source_unavailable' and first['notify_source_failure'] is True
    saved = copy.deepcopy(store.load())
    assert saved['next_day'] == DAY.isoformat() and saved['pending'] is None
    assert saved['collecting']['counts'] == {'getBaseInfoByPeriod': 1}
    assert saved['source_retry']['source'] == 'getEventByPeriod'
    assert store.db.get(SystemState, 'egr_last_sync_date') is None
    refresh.assert_not_called()
    resumed = PeriodSyncStore(store.db)
    assert execute(resumed, client, refresh, 1100)['status'] == 'cooldown'
    assert resumed.load() == saved
    assert client.get_period_rows.await_count == 2
    second = execute(resumed, client, refresh, 4600)
    assert second['notify_source_failure'] is False and second['retry_after_seconds'] == 7200
    assert client.get_period_rows.await_count == 3
    fail[0] = False
    assert execute(resumed, client, refresh, 11800)['status'] == 'complete'
    assert [call.args[0] for call in client.get_period_rows.await_args_list].count('getBaseInfoByPeriod') == 1
    refresh.assert_awaited_once_with(193879557)
    assert 'source_retry' not in resumed.load() and 'collecting' not in resumed.load()
    assert store.db.get(SystemState, 'egr_last_sync_date').value == DAY.isoformat()


def test_first_feed_timeout_is_identified_without_advancing_checkpoint(store):
    client = Mock(get_period_rows=AsyncMock(side_effect=httpx.ConnectTimeout('down')))
    result = execute(store, client, AsyncMock(), 1000)
    assert result['source'] == 'getBaseInfoByPeriod'
    assert store.load()['collecting']['counts'] == {}
    assert store.load()['completed_target'] is None


def test_repeated_failure_backoff_is_capped_and_never_marks_day_complete(store):
    client = Mock(get_period_rows=AsyncMock(side_effect=httpx.ReadTimeout('down')))
    for now, seconds in [(1000,3600),(4600,7200),(11800,14400),(26200,14400)]:
        result = execute(store, client, AsyncMock(), now)
        assert result['retry_after_seconds'] == seconds
        assert result['notify_source_failure'] is (now == 1000)
        assert store.load()['next_day'] == DAY.isoformat()
        assert store.db.get(SystemState,'egr_last_sync_date') is None


def test_invalid_configuration_stays_loud_even_during_cooldown(store):
    client = Mock(get_period_rows=AsyncMock(side_effect=httpx.ReadTimeout('down')))
    execute(store, client, AsyncMock(), 1000)
    with pytest.raises(ValueError, match='Invalid EGR period sync limits'):
        asyncio.run(run_period_sync(store, client, AsyncMock(), target=DAY,
                                    max_companies=0, clock=lambda:1100))


def test_exhausted_budget_without_source_work_does_not_clear_outage(store, monkeypatch):
    client = Mock(get_period_rows=AsyncMock(side_effect=httpx.ReadTimeout('down')))
    execute(store, client, AsyncMock(), 1000)
    before = copy.deepcopy(store.load())
    # Replace only this module's clock, not asyncio's process-wide time module.
    monkeypatch.setattr('app.services.egr_period_sync.time',
                        SimpleNamespace(monotonic=Mock(side_effect=[0, 2])))
    result = asyncio.run(run_period_sync(store, client, AsyncMock(), target=DAY,
                                         max_seconds=1, clock=lambda:4600))
    assert result['status'] == 'pending'
    assert store.load() == before
    assert client.get_period_rows.await_count == 1


@pytest.mark.parametrize('status', [429, 500, 502, 503, 504])
def test_transient_http_outage_obeys_retry_after(store, status):
    request = httpx.Request('GET', 'https://egr.gov.by/api/v2/egr/getEventByPeriod/07.10.2026/07.10.2026')
    response = httpx.Response(status, request=request, headers={'Retry-After': '9000'})
    error = httpx.HTTPStatusError('down', request=request, response=response)
    client = Mock(get_period_rows=AsyncMock(side_effect=error))
    result = execute(store, client, AsyncMock(), 1000)
    assert result['status'] == 'source_unavailable' and result['retry_after_seconds'] == 9000
    assert execute(store, client, AsyncMock(), 9000)['status'] == 'cooldown'
    assert client.get_period_rows.await_count == 1


@pytest.mark.parametrize('error', [ValueError('invalid JSON'), RuntimeError('db failure'),
    httpx.HTTPStatusError('auth', request=httpx.Request('GET','https://example.test'), response=httpx.Response(403))])
def test_schema_auth_and_programming_errors_are_not_silenced(store, error):
    with pytest.raises(type(error)):
        execute(store, Mock(get_period_rows=AsyncMock(side_effect=error)), AsyncMock(), 1000)
    assert 'source_retry' not in store.load()


def test_company_timeout_retries_same_unp_without_refetching_feeds(store):
    client = Mock(get_period_rows=AsyncMock(side_effect=lambda source, day:
        [{'ngrn': 193879557}] if source == 'getBaseInfoByPeriod' else []))
    result = execute(store, client, AsyncMock(side_effect=httpx.ReadTimeout('down')), 1000)
    assert result['status'] == 'source_unavailable'
    assert store.load()['pending']['next_index'] == 0
    refresh = AsyncMock()
    assert execute(store, client, refresh, 4600)['status'] == 'complete'
    refresh.assert_awaited_once_with(193879557)
    assert client.get_period_rows.await_count == len(PERIOD_SOURCES)


@pytest.mark.parametrize('notify', [True, False])
def test_daily_outage_alert_is_sent_only_once_per_incident(monkeypatch, notify):
    from app.tasks import parser_alerts
    send = Mock()
    monkeypatch.setattr(parser_alerts, 'send_telegram_alert', send)
    parser_alerts.parser_task_finished(sender=SimpleNamespace(name='app.tasks.sync_tasks.sync_daily_changes'),
        state='SUCCESS', retval={'status':'source_unavailable','notify_source_failure':notify})
    assert send.call_count == int(notify)


def test_other_source_alerts_are_not_suppressed(monkeypatch):
    from app.tasks import parser_alerts
    send = Mock()
    monkeypatch.setattr(parser_alerts, 'send_telegram_alert', send)
    parser_alerts.parser_task_finished(sender=SimpleNamespace(name='app.tasks.nalog_debt_tasks.sync_nalog_debt'),
        state='SUCCESS', retval={'status':'source_unavailable','notify_source_failure':False})
    send.assert_called_once()
