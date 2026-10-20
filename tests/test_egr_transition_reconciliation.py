"""Incomplete transitions cannot freeze new days or create invented links."""
import asyncio
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.database.models import SystemState
from app.services.egr_client import EGRClient
from app.services.egr_period_sync import PeriodSyncStore, run_period_sync, validate_period_rows
from app.services.egr_transition_reconciliation import SOURCE, resolution_candidate

DAY = date(2026, 10, 13)
JUR = 193879557
IP = 300325070
RAW = {"ulngrn": JUR, "dreg": "13.10.2026", "vfio": "Original source value"}
FULL = {**RAW, "ipngrn": IP}


@pytest.fixture
def store():
    engine = create_engine("sqlite://")
    SystemState.__table__.create(engine)
    with engine.begin() as connection:
        # Exercise the real relationship upsert and checkpoint transaction on a
        # lightweight SQL backend; no production DB or network is contacted.
        connection.execute(text("""CREATE TABLE egr_ip_to_jur (
            ip_unp BIGINT NOT NULL, jur_unp BIGINT NOT NULL,
            registration_date DATE, raw TEXT NOT NULL,
            last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ip_unp, jur_unp))"""))
    with Session(engine) as db:
        yield PeriodSyncStore(db)
    engine.dispose()


def client_for(rows):
    async def fetch(source, day):
        return rows if source == SOURCE and day == DAY.strftime("%d.%m.%Y") else []
    return Mock(get_period_rows=AsyncMock(side_effect=fetch))


def run(store, client, refresh=None, now=1000, **overrides):
    kwargs = dict(target=DAY, bootstrap_days=1, delay=0, clock=lambda: now)
    kwargs.update(overrides)
    return asyncio.run(run_period_sync(store, client, refresh or AsyncMock(), **kwargs))


def links(store):
    return store.db.execute(text("SELECT ip_unp, jur_unp FROM egr_ip_to_jur ORDER BY ip_unp")).all()


@pytest.mark.parametrize("bad", [None, "", 0, -1, True, False, 1.1, "bad", 1_000_000_000])
def test_bad_identifier_is_losslessly_quarantined_and_known_company_refreshed(store, bad):
    raw = {**RAW, "ipngrn": bad}
    refresh = AsyncMock()
    result = run(store, client_for([raw]), refresh)
    refresh.assert_awaited_once_with(JUR)
    assert result["status"] == "blocked"
    assert result["unresolved_transitions"] == 1
    assert result["notify_transition_conflicts"] is True
    state = store.load()
    item = next(iter(state["transition_conflicts"].values()))
    assert item["raw"] == raw and item["invalid_fields"] == ["ipngrn"]
    assert item["attempts"] == 0 and item["next_retry_at"] == 4600
    assert state["completed_target"] is None
    assert state["last_completed_day"] is None
    assert state["scanned_through"] == DAY.isoformat()
    assert store.db.get(SystemState, "egr_last_sync_date") is None
    assert links(store) == []


def test_eight_good_links_and_one_missing_id_do_not_block_other_companies(store):
    good = [{**FULL, "ipngrn": IP + i} for i in range(8)]
    refresh = AsyncMock()
    result = run(store, client_for([RAW, *good]), refresh)
    assert len(links(store)) == 8
    assert refresh.await_count == 9
    assert result["status"] == "blocked" and result["unresolved_transitions"] == 1
    assert next(iter(store.load()["transition_conflicts"].values()))["raw"] == RAW


def test_reverse_partial_transition_refreshes_known_ip_without_inventing_jur(store):
    refresh = AsyncMock()
    raw = {"ipngrn": IP, "dreg": "13.10.2026"}
    run(store, client_for([raw]), refresh)
    refresh.assert_awaited_once_with(IP)
    assert links(store) == []


@pytest.mark.parametrize("rows", [{}, [None], [{}], [{"ipngrn": 0, "ulngrn": "bad"}]])
def test_unrecognizable_schema_remains_an_error(rows):
    with pytest.raises(ValueError):
        validate_period_rows(SOURCE, rows)


def test_real_client_preserves_incomplete_payload_instead_of_rejecting_it():
    async def check():
        client = EGRClient()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json=[RAW])))
        try:
            assert await client.get_period_rows(SOURCE, "13.10.2026") == [RAW]
        finally:
            await client.close()
    asyncio.run(check())


def test_future_days_continue_while_watermark_stays_before_first_gap(store):
    client = client_for([RAW])
    run(store, client, target=DAY, bootstrap_days=2)
    assert store.load()["last_completed_day"] == "2026-10-12"
    client.get_period_rows.reset_mock()
    result = run(store, client, now=2000, target=DAY + timedelta(days=2))
    assert result["status"] == "blocked" and result["notify_transition_conflicts"] is False
    assert len(client.get_period_rows.await_args_list) == 16
    state = store.load()
    assert state["scanned_through"] == "2026-10-15"
    assert state["next_day"] is None and state["target"] == "2026-10-15"
    assert state["last_completed_day"] == "2026-10-12"
    assert store.db.get(SystemState, "egr_last_sync_date").value == "2026-10-12"


def test_restart_resolution_retries_only_affected_feed_refreshes_both_and_advances(store):
    run(store, client_for([RAW]))
    with Session(store.db.bind) as db:
        resumed = PeriodSyncStore(db)
        client = client_for([FULL])
        refresh = AsyncMock()
        result = run(resumed, client, refresh, now=4600)
        assert result["status"] == "complete" and result["notify_transition_conflicts"] is True
        client.get_period_rows.assert_awaited_once_with(SOURCE, "13.10.2026")
        assert {call.args[0] for call in refresh.await_args_list} == {JUR, IP}
        assert links(resumed) == [(IP, JUR)]
        assert resumed.load()["transition_conflicts"] == {}
        audit = next(iter(resumed.load()["transition_resolutions"].values()))
        assert audit["raw"] == RAW and audit["resolution"] == FULL
        assert db.get(SystemState, "egr_last_sync_date").value == DAY.isoformat()
        assert run(resumed, client, now=4700)["status"] == "up_to_date"
        assert client.get_period_rows.await_count == 1
        assert run(resumed, client, now=4800, target=DAY + timedelta(days=1))["status"] == "complete"
        assert next(iter(resumed.load()["transition_resolutions"].values()))["raw"] == RAW


def test_partial_retry_preserves_raw_and_backs_off_without_repeating_alert(store):
    run(store, client_for([RAW]))
    client = client_for([RAW])
    assert run(store, client, now=2000)["notify_transition_conflicts"] is False
    client.get_period_rows.assert_not_called()
    result = run(store, client, now=4600)
    assert result["notify_transition_conflicts"] is False
    item = next(iter(store.load()["transition_conflicts"].values()))
    assert item["raw"] == RAW and item["attempts"] == 1
    assert item["next_retry_at"] == 11800
    assert run(store, client, now=5000)["status"] == "blocked"
    assert client.get_period_rows.await_count == 1


def test_retry_outage_is_separate_and_does_not_freeze_new_day(store):
    run(store, client_for([RAW]))
    client = client_for([])
    original = client.get_period_rows.side_effect
    async def fetch(source, day):
        if source == SOURCE and day == "13.10.2026":
            raise httpx.ReadTimeout("temporary")
        return await original(source, day)
    client.get_period_rows.side_effect = fetch
    result = run(store, client, now=4600, target=DAY + timedelta(days=1))
    assert result["status"] == "blocked"
    item = next(iter(store.load()["transition_conflicts"].values()))
    assert item["last_error"] == "ReadTimeout"
    assert store.load()["scanned_through"] == "2026-10-14"
    assert "source_retry" not in store.load()


def test_new_bad_rows_on_retry_are_preserved_too(store):
    run(store, client_for([RAW]))
    other = {**RAW, "ulngrn": JUR + 1}
    result = run(store, client_for([RAW, other]), now=4600)
    assert result["unresolved_transitions"] == 2
    assert result["notify_transition_conflicts"] is True
    assert {item["raw"]["ulngrn"] for item in store.load()["transition_conflicts"].values()} == {JUR, JUR + 1}


@pytest.mark.parametrize("rows", [[], [RAW], [{**FULL, "vfio": "Changed value"}],
                                  [FULL, {**FULL, "ipngrn": IP + 1}]])
def test_no_resolution_from_disappearance_changed_name_or_ambiguous_candidate(rows):
    item = {"raw": RAW, "invalid_fields": ["ipngrn"]}
    assert resolution_candidate(item, rows) is None


def test_identical_duplicate_source_rows_are_not_ambiguous():
    assert resolution_candidate({"raw": RAW, "invalid_fields": ["ipngrn"]}, [FULL, FULL]) == FULL


def test_small_budget_and_crash_resume_candidate_without_refetch(store):
    run(store, client_for([RAW]))
    client = client_for([FULL])
    refresh = AsyncMock()
    # First request exhausts the reconciliation budget; the candidate is saved.
    assert run(store, client, refresh, now=4600, max_companies=1)["status"] == "blocked"
    assert next(iter(store.load()["transition_conflicts"].values()))["candidate"] == FULL
    assert run(store, client, refresh, now=4601, max_companies=1)["status"] == "blocked"
    assert links(store) == []
    assert run(store, client, refresh, now=4602, max_companies=1)["status"] == "complete"
    assert refresh.await_count == 2 and client.get_period_rows.await_count == 1


def test_relationship_and_queue_ack_roll_back_together(store, monkeypatch):
    run(store, client_for([RAW]))
    before = store.load()
    commit = store.db.commit
    def fail_commit():
        # Fail only the commit which has removed the quarantined row.
        checkpoint = store.db.query(SystemState).filter(SystemState.key == store.state_key).first()
        import json
        if not json.loads(checkpoint.value).get("transition_conflicts"):
            raise RuntimeError("commit failed")
        commit()
    monkeypatch.setattr(store.db, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        run(store, client_for([FULL]), now=4600)
    assert links(store) == []
    assert next(iter(store.load()["transition_conflicts"].values()))["raw"] == RAW
    assert store.load()["last_completed_day"] == before["last_completed_day"]
    monkeypatch.setattr(store.db, "commit", commit)
    assert run(store, client_for([FULL]), now=4601)["status"] == "complete"
    assert links(store) == [(IP, JUR)]


def test_replaying_partial_collection_keeps_one_quarantine_entry(store):
    run(store, client_for([RAW, RAW]))
    assert len(store.load()["transition_conflicts"]) == 1


@pytest.mark.parametrize("count,notify,expected", [(1, True, 1), (1, False, 0), (0, True, 1)])
def test_notifications_are_only_for_changed_queue_state(monkeypatch, count, notify, expected):
    from app.tasks import parser_alerts
    send = Mock()
    monkeypatch.setattr(parser_alerts, "send_telegram_alert", send)
    parser_alerts.parser_task_finished(
        sender=SimpleNamespace(name="app.tasks.sync_tasks.sync_daily_changes"), state="SUCCESS",
        retval={"status": "blocked" if count else "complete", "unresolved_transitions": count,
                "notify_transition_conflicts": notify, "scanned_through": DAY.isoformat()},
    )
    assert send.call_count == expected
    if expected:
        assert "Original source value" not in send.call_args.args[0]


def test_persistence_rejects_a_partial_relationship_even_when_called_directly(store):
    with pytest.raises(ValueError, match="incomplete"):
        store.save({"version": 2}, transitions=[RAW])
    assert links(store) == [] and store.load() is None


def test_production_checkpoint_with_seven_collected_feeds_resumes_only_eighth(store):
    from app.services.egr_period_sync import PERIOD_SOURCES
    store.save({
        "version": 2, "target": DAY.isoformat(), "next_day": DAY.isoformat(),
        "pending": None, "completed_target": "2026-10-12", "last_completed_day": "2026-10-12",
        "collecting": {"day": DAY.isoformat(), "unps": [JUR], "events": {}, "transitions": [],
                       "counts": {key: 0 for key in PERIOD_SOURCES if key != SOURCE}},
    })
    client = client_for([RAW])
    refresh = AsyncMock()
    result = run(store, client, refresh)
    assert result["status"] == "blocked"
    client.get_period_rows.assert_awaited_once_with(SOURCE, "13.10.2026")
    refresh.assert_awaited_once_with(JUR)
    assert next(iter(store.load()["transition_conflicts"].values()))["raw"] == RAW


def test_reconciliation_budget_reserves_room_for_new_days(store):
    run(store, client_for([RAW]))
    refresh = AsyncMock()
    client = client_for([FULL])
    original = client.get_period_rows.side_effect
    async def fetch(source, day):
        if source == "getAddressByPeriod" and day == "14.10.2026":
            return [{"ngrn": JUR + 1}]
        return await original(source, day)
    client.get_period_rows.side_effect = fetch
    result = run(store, client, refresh, now=4600, target=DAY + timedelta(days=1), max_companies=5)
    # Feed retry used the one reserved unit; candidate refresh waits, new day runs.
    assert result["status"] == "blocked"
    refresh.assert_awaited_once_with(JUR + 1)
    assert store.load()["scanned_through"] == "2026-10-14"
    assert links(store) == []
    assert run(store, client, now=4601, target=DAY + timedelta(days=1))["status"] == "complete"


def test_reconciliation_company_timeout_does_not_freeze_new_day(store):
    run(store, client_for([RAW]))
    client = client_for([FULL])
    refresh = AsyncMock(side_effect=httpx.ReadTimeout("temporary card timeout"))
    result = run(store, client, refresh, now=4600, target=DAY + timedelta(days=1))
    assert result["status"] == "blocked"
    assert store.load()["scanned_through"] == "2026-10-14"
    item = next(iter(store.load()["transition_conflicts"].values()))
    assert item["last_error"] == "ReadTimeout" and "candidate" not in item
    assert links(store) == [] and "source_retry" not in store.load()


def test_success_result_is_not_reported_when_alert_success_setting_enabled(monkeypatch):
    from app.tasks import parser_alerts
    monkeypatch.setattr(parser_alerts.settings, "PARSER_ALERTS_NOTIFY_SUCCESS", True)
    send = Mock()
    monkeypatch.setattr(parser_alerts, "send_telegram_alert", send)
    parser_alerts.parser_task_finished(
        sender=SimpleNamespace(name="app.tasks.sync_tasks.sync_daily_changes"), state="SUCCESS",
        retval={"status": "blocked", "unresolved_transitions": 1,
                "notify_transition_conflicts": False},
    )
    send.assert_not_called()
