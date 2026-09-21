import asyncio
import json
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
import requests

from app.services.egr_client import MobileEGRClient
from app.services import nalog_debt as debt, eaeu_sez as sez, eaeu_sez_fetch as sez_fetch, licenses


@pytest.mark.parametrize("status,body,expected", [(204, "", None), (404, "", None), (200, "Minsk", "Minsk")])
def test_mobile_empty_is_not_an_error(status, body, expected):
    async def run():
        client = MobileEGRClient()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(status, text=body)))
        try:
            assert await client.get_place_location("100000001", strict=True) == expected
        finally:
            await client.close()
    asyncio.run(run())


def test_mobile_strict_mode_distinguishes_503_from_empty():
    async def run():
        client = MobileEGRClient()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(503)))
        try:
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_place_location("100000001", strict=True)
            assert await client.get_place_location("100000001") is None
        finally:
            await client.close()
    asyncio.run(run())


@pytest.mark.parametrize("payload", ['{}', '{"error":"unavailable"}', '[1]', '{"items":[1]}', '//OK[2,1,["type","{}"],0,7]'])
def test_malformed_debt_response_is_not_a_valid_empty_slice(payload):
    with pytest.raises(debt.GwtRpcParseError):
        debt.extract_items(payload)


def test_valid_empty_debt_response():
    assert debt.extract_items('//OK[2,1,["type","[]"],0,7]') == []


def test_empty_fetch_preserves_good_file(monkeypatch, tmp_path):
    path = tmp_path / "2026-09-01.json"
    original = '{"items":[{"unp":"100000001"}]}'
    path.write_text(original)
    session = Mock()
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock()
    monkeypatch.setattr(debt, "make_session", lambda **kw: session)
    monkeypatch.setattr(debt, "fetch_all_for_date_one_region", lambda **kw: [])
    with pytest.raises(debt.EmptyDebtSliceError):
        debt.process_one_date(date(2026, 9, 1), "A" * 32, None, None, tmp_path,
                              1, 0, True, False, 0, 0, tmp_path / "errors")
    assert path.read_text() == original


def test_monthly_empty_refreshes_previous_without_relabelling(monkeypatch, tmp_path):
    calls, imported = [], []
    def fetch(**kwargs):
        calls.append(kwargs)
        if kwargs["start_date"] == "2026-09-01":
            raise debt.EmptyDebtSliceError()
    monkeypatch.setattr(debt, "run_fetcher", fetch)
    monkeypatch.setattr(debt, "load_json_file_to_db", lambda path, db, **kw: imported.append(path.name) or 8)
    result = debt.refresh_latest_debt_slice(Mock(), tmp_path, today=date(2026, 9, 14))
    assert result["status"] == "source_empty"
    assert result["refreshed_slice"] == "2026-08-01"
    assert imported == ["2026-08-01.json"]
    assert all(call["allow_empty_slices"] is False for call in calls)


def test_monthly_transport_error_never_imports_old_file(monkeypatch, tmp_path):
    def fail(**kw):
        raise requests.ConnectionError("unavailable")
    monkeypatch.setattr(debt, "run_fetcher", fail)
    importer = Mock()
    monkeypatch.setattr(debt, "load_json_file_to_db", importer)
    with pytest.raises(requests.ConnectionError):
        debt.refresh_latest_debt_slice(Mock(), tmp_path)
    importer.assert_not_called()


def test_debt_invalid_row_rejected_before_delete(tmp_path):
    path = tmp_path / "2026-09-01.json"
    path.write_text(json.dumps({"items": [{"unp": "100000001"}, {"unp": "bad"}]}))
    db = Mock()
    with pytest.raises(ValueError, match="Invalid UNP"):
        debt.load_json_file_to_db(path, db, replace_existing_slice=True)
    db.query.assert_not_called()
    db.execute.assert_not_called()


def test_sez_source_failure_does_not_reimport_old_snapshot(monkeypatch, tmp_path):
    path = tmp_path / "sez.json"
    path.write_text('[{"item_id":1}]')
    monkeypatch.setattr(sez.settings, "SEZ_SNAPSHOT_PATH", str(path))
    def fail(**kw):
        raise RuntimeError("404")
    monkeypatch.setattr(sez_fetch, "fetch_rows", fail)
    importer = Mock()
    monkeypatch.setattr(sez, "import_sez_snapshot_rows", importer)
    db = Mock()
    db.query.return_value.count.return_value = 1016
    result = sez.sync_eaeu_sez_residents(db)
    assert result["status"] == "source_unavailable"
    assert result["preserved_records"] == 1016
    importer.assert_not_called()
    db.commit.assert_not_called()


def test_sez_unrecognized_response_fails(monkeypatch):
    session = Mock()
    session.post.return_value.text = '<string>not a registry</string>'
    with pytest.raises(RuntimeError, match="1 attempts"):
        sez_fetch.fetch_page(session, None, 1, 0)


@pytest.fixture
def license_db():
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from app.database.models import SystemState
    engine = create_engine("sqlite://")
    SystemState.__table__.create(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_license_cursor_advances_and_wraps(monkeypatch, license_db):
    calls = []
    def fetch(page, size, **kw):
        calls.append(page)
        return {"items": [{"id": page}], "pageCount": 3, "count": 3}
    monkeypatch.setattr(licenses, "fetch_license_page", fetch)
    monkeypatch.setattr(licenses, "import_license_rows", lambda db, rows: {"saved": len(rows), "total": len(rows)})
    monkeypatch.setattr(licenses.settings, "LICENSE_CHECK_PAGES", 2)
    monkeypatch.setattr(licenses.settings, "LICENSE_PAGE_DELAY_SECONDS", 0)
    first = licenses.check_license_api_changes(license_db, page_size=1)
    assert first["next_page"] == 3 and not first["cycle_complete"]
    second = licenses.check_license_api_changes(license_db, page_size=1)
    assert calls == [1, 2, 3]
    assert second["next_page"] == 1 and second["cycle_complete"]


def test_license_failed_page_is_replayed(monkeypatch, license_db):
    from sqlalchemy import text
    calls = []
    def fetch(page, size, **kw):
        calls.append(page)
        if page == 2:
            raise requests.ConnectionError("network")
        return {"items": [{"id": page}], "pageCount": 3}
    monkeypatch.setattr(licenses, "fetch_license_page", fetch)
    monkeypatch.setattr(licenses, "import_license_rows", lambda db, rows: {"saved": 1})
    monkeypatch.setattr(licenses.settings, "LICENSE_CHECK_PAGES", 3)
    monkeypatch.setattr(licenses.settings, "LICENSE_PAGE_DELAY_SECONDS", 0)
    with pytest.raises(requests.ConnectionError):
        licenses.check_license_api_changes(license_db, page_size=1)
    license_db.rollback()
    assert license_db.execute(text("SELECT value FROM egr_system_state WHERE key='license_check_next_page'")).scalar() == "2"
    assert calls == [1, 2]


def test_address_task_saves_attempts_without_overwriting_empty_or_failed_rows(monkeypatch):
    from app.tasks import sync_tasks
    db = Mock()
    monkeypatch.setattr(sync_tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(sync_tasks, "select_due_unps", lambda *args: [1, 2, 3])
    attempts = Mock()
    monkeypatch.setattr(sync_tasks, "record_attempt", attempts)
    class Mobile:
        def __init__(self, *args): pass
        async def close(self): pass
        async def get_place_location(self, unp, *, strict):
            assert strict
            if unp == "3":
                raise httpx.ConnectError("offline")
            return "Minsk" if unp == "1" else None
    monkeypatch.setattr(sync_tasks, "MobileEGRClient", Mobile)
    assert sync_tasks.egr_sync_place_locations.run(batch_size=3, parallel=1) == 1
    assert [call.args[3] for call in attempts.call_args_list] == ["success", "empty", "error"]
    assert db.execute.call_count == 1
    assert db.execute.call_args.args[1]["unp"] == 1
    db.commit.assert_called_once()


def test_grp_task_classifies_empty_responses_as_negative_cache(monkeypatch):
    from app.tasks import sync_tasks
    db = Mock()
    monkeypatch.setattr(sync_tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(sync_tasks, "select_due_unps", lambda *args: [1, 2])
    attempts = Mock()
    monkeypatch.setattr(sync_tasks, "record_attempt", attempts)
    async def fetch(client, unp, *args):
        return (unp, {"VUNP": unp}, 200, None) if unp == 1 else (unp, None, 404, "GRP returned empty payload")
    monkeypatch.setattr(sync_tasks, "_grp_one_with_retry", fetch)
    assert sync_tasks.grp_fetch_raw.run(limit=2, batch_size=2) == 2
    assert [call.args[3] for call in attempts.call_args_list] == ["success", "empty"]
    db.commit.assert_called_once()


@pytest.mark.parametrize("target", ["https://example.org/steal", "http://lkfl.portal.nalog.gov.by/debtor/dispatch/SearchDataAction",
                                     "https://lkfl.portal.nalog.gov.by/login"])
def test_debt_does_not_follow_unexpected_redirects(target):
    session = Mock()
    response = requests.Response()
    response.status_code = 302
    response.headers["Location"] = target
    session.post.return_value = response
    with pytest.raises(debt.GwtRpcParseError, match="redirect"):
        debt._post_with_redirect_handling(session, debt.DISPATCH_URL, b"query", 1)
    assert session.post.call_count == 1


def test_license_short_intermediate_page_is_not_completion(monkeypatch, license_db):
    monkeypatch.setattr(licenses, "fetch_license_page", lambda *a, **kw: {"items": [{"id": 1}], "pageCount": 4})
    monkeypatch.setattr(licenses, "import_license_rows", Mock())
    with pytest.raises(ValueError, match="Incomplete"):
        licenses.check_license_api_changes(license_db, pages=1, page_size=2)
    licenses.import_license_rows.assert_not_called()


def test_sez_permanent_404_is_not_retried():
    session = Mock()
    response = requests.Response()
    response.status_code = 404
    session.post.return_value = response
    with pytest.raises(RuntimeError, match="1 attempts"):
        sez_fetch.fetch_page(session, None, 1, 3)
    assert session.post.call_count == 1


def test_source_fetch_migration_adds_only_retry_metadata(monkeypatch):
    import importlib.util
    import io
    from alembic.operations import Operations
    from alembic.migration import MigrationContext
    path = Path(__file__).resolve().parents[1] / "migrations/versions/sourcefetch1_add_source_fetch_attempts.py"
    spec = importlib.util.spec_from_file_location("source_fetch_migration_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    monkeypatch.setattr(module, "op", Operations(context))
    module.upgrade()
    sql = output.getvalue()
    assert sql.count("CREATE TABLE") == 1
    assert "CREATE INDEX ix_source_fetch_attempts_due" in sql
    assert "DROP " not in sql and "DELETE " not in sql and "ALTER TABLE" not in sql


def test_source_empty_sends_warning_not_success(monkeypatch):
    from app.tasks import parser_alerts
    from types import SimpleNamespace
    send = Mock()
    monkeypatch.setattr(parser_alerts, "send_telegram_alert", send)
    monkeypatch.setattr(parser_alerts.settings, "PARSER_ALERTS_NOTIFY_SUCCESS", False)
    parser_alerts.parser_task_finished(
        sender=SimpleNamespace(name="app.tasks.nalog_debt_tasks.sync_nalog_debt"),
        state="SUCCESS", retval={"status": "source_empty", "refreshed_slice": "2026-08-01"},
    )
    send.assert_called_once()
    assert "⚠️" in send.call_args.args[0] and "✅" not in send.call_args.args[0]
