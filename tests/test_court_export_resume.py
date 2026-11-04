"""Exercise resumable export without contacting the court service."""
import json
import sys

import pytest

from app.services.court_judgments import CourtAuthenticationError, CourtJudgment
from app.services.court_judgments import CourtResponseError
import requests
from scripts import export_court_judgments as exporter


def test_cli_defaults_match_thirty_second_client_delay(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["export_court_judgments.py", "--cookie-stdin"])
    args = exporter.parse_args()
    with exporter.CourtJudgmentClient("a=b") as client:
        assert args.delay == client.min_interval_seconds == 30
        assert args.delay_jitter == client.delay_jitter_seconds == 0


def record(page):
    return CourtJudgment(
        key=f"document:{page}", court_id=151, court="Test court",
        case_number="one-process", document_type="Decision", judgment_date="2025-01-01",
        resolution="Test resolution", download_url=None, process_id="100",
        document_id=str(page), source_page=page,
    )


def setup_run(monkeypatch, tmp_path):
    cookie = tmp_path / "cookie.txt"
    cookie.write_text("a=b", encoding="utf-8")
    args = ["export_court_judgments.py", "--cookie-file", str(cookie),
            "--output-dir", str(tmp_path), "--court", "151"]

    class Client:
        fail = None
        calls = []
        def __init__(self, *_args, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def fetch_page(self, filters, page):
            self.calls.append(page)
            if self.fail == page:
                raise CourtAuthenticationError("Expired")
            return [record(page)], 3

    monkeypatch.setattr(exporter, "CourtJudgmentClient", Client)
    monkeypatch.setattr(sys, "argv", args)
    return Client, args


def test_cli_rejects_less_than_thirty_seconds_before_export(monkeypatch, tmp_path):
    client, args = setup_run(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", args + ["--delay", "4.9"])
    with pytest.raises(ValueError, match="at least 5 seconds"):
        exporter.main()
    assert client.calls == []


def test_page_limit_keeps_checkpoint_then_resume_finishes(monkeypatch, tmp_path):
    client, args = setup_run(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", args + ["--max-pages", "1"])
    assert exporter.main() == 0
    assert client.calls == [1]
    assert not list(tmp_path.glob("*.jsonl"))
    assert len(list(tmp_path.glob("*.state.json"))) == 1
    monkeypatch.setattr(sys, "argv", args)
    assert exporter.main() == 0
    assert client.calls == [1, 2, 3]
    output = next(tmp_path.glob("*.jsonl"))
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(rows) == len({row["key"] for row in rows}) == 3
    assert not list(tmp_path.glob("*.state.json"))


def test_expired_cookie_keeps_completed_page(monkeypatch, tmp_path):
    client, _ = setup_run(monkeypatch, tmp_path)
    client.fail = 2
    assert exporter.main() == 2
    assert client.calls == [1, 2]
    state = json.loads(next(tmp_path.glob("*.state.json")).read_text())
    assert state["completed_pages"] == {"151": [1]}
    assert len(next(tmp_path.glob("*.partial")).read_text().splitlines()) == 1
    client.fail = None
    assert exporter.main() == 0
    assert client.calls == [1, 2, 2, 3]


def test_empty_court_is_checkpointed_and_skipped_after_resume(monkeypatch, tmp_path):
    client, args = setup_run(monkeypatch, tmp_path)
    client.fail = True

    def fetch_page(self, filters, page):
        self.calls.append((filters.court, page))
        if filters.court == 151:
            return [], 1
        if self.fail:
            raise CourtAuthenticationError("Expired")
        return [record(page)], 3

    monkeypatch.setattr(client, "fetch_page", fetch_page)
    monkeypatch.setattr(sys, "argv", args + ["--court", "152", "--max-pages", "1"])
    assert exporter.main() == 2
    state = json.loads(next(tmp_path.glob("*.state.json")).read_text())
    assert state["completed_pages"]["151"] == [1]
    assert state["total_pages"]["151"] == 1
    assert next(tmp_path.glob("*.partial")).read_text() == ""

    client.fail = False
    assert exporter.main() == 0
    assert client.calls == [(151, 1), (152, 1), (152, 1)]
    state = json.loads(next(tmp_path.glob("*.state.json")).read_text())
    assert state["completed_pages"] == {"151": [1], "152": [1]}
    assert len(next(tmp_path.glob("*.partial")).read_text().splitlines()) == 1


@pytest.mark.parametrize("delivered", [True, False])
def test_auth_alert_preserves_exit_code_and_checkpoint(monkeypatch, tmp_path, delivered, capsys):
    client, args = setup_run(monkeypatch, tmp_path)
    client.fail = 2
    alerts = []
    monkeypatch.setattr(exporter, "telegram_configured", lambda: True)
    def notify(**kwargs):
        alerts.append(kwargs)
        return delivered
    monkeypatch.setattr(exporter, "notify_auth_failure", notify)
    monkeypatch.setattr(sys, "argv", args + ["--notify-telegram"])
    assert exporter.main() == 2
    assert alerts == [{"court_id": 151, "type_proc": 14, "unique_total": 1,
                       "page": 2, "pages_completed": 1, "pages_total": 3,
                       "current_pages_completed": 1, "current_pages_total": 3,
                       "cookie_file": tmp_path / "cookie.txt"}]
    state = json.loads(next(tmp_path.glob("*.state.json")).read_text())
    assert state["completed_pages"] == {"151": [1]}
    assert ("notification: sent" if delivered else "notification: NOT delivered") in capsys.readouterr().err
    client.fail = None
    assert exporter.main() == 0
    assert len(alerts) == 1


def test_alerts_are_opt_in(monkeypatch, tmp_path):
    client, _ = setup_run(monkeypatch, tmp_path)
    client.fail = 1
    def unexpected(**kwargs):
        pytest.fail("Alerts must not be sent without --notify-telegram")
    monkeypatch.setattr(exporter, "notify_auth_failure", unexpected)
    assert exporter.main() == 2


def test_missing_alert_config_fails_before_court_request(monkeypatch, tmp_path):
    client, args = setup_run(monkeypatch, tmp_path)
    monkeypatch.setattr(exporter, "telegram_configured", lambda: False)
    monkeypatch.setattr(sys, "argv", args + ["--notify-telegram"])
    with pytest.raises(ValueError, match="ALERT_TELEGRAM_BOT_TOKEN"):
        exporter.main()
    assert client.calls == []


@pytest.mark.parametrize("error", [RuntimeError("response secret-cookie-value"),
                                    OSError("secret-cookie-value")])
@pytest.mark.parametrize("delivered", [True, False])
def test_non_auth_error_notifies_keeps_checkpoint_and_can_resume(monkeypatch, tmp_path, capsys, error, delivered):
    client, args = setup_run(monkeypatch, tmp_path)
    original_fetch = client.fetch_page
    def fetch(self, filters, page):
        if page == 2:
            raise error
        return original_fetch(self, filters, page)
    monkeypatch.setattr(client, "fetch_page", fetch)
    monkeypatch.setattr(exporter, "telegram_configured", lambda: True)
    monkeypatch.setattr(exporter, "notifications_managed", lambda _: True)
    monkeypatch.setattr(exporter, "notify_auth_failure", lambda **kw: pytest.fail("Not an auth failure"))
    calls = []
    monkeypatch.setattr(exporter, "notify_export_failure", lambda **kw: calls.append(kw) or delivered)
    monkeypatch.setattr(sys, "argv", args + ["--notify-telegram"])
    assert exporter.main() == 1
    assert calls == [{"court_id": 151, "type_proc": 14, "page": 2,
                      "unique_total": 1, "error_type": type(error).__name__,
                      "pages_completed": 1, "pages_total": 3,
                      "current_pages_completed": 1, "current_pages_total": 3}]
    assert "secret-cookie-value" not in capsys.readouterr().err
    state = json.loads(next(tmp_path.glob("*.state.json")).read_text())
    assert state["completed_pages"] == {"151": [1]}
    assert not list(tmp_path.glob("*.jsonl"))
    monkeypatch.setattr(client, "fetch_page", original_fetch)
    assert exporter.main() == 0
    assert len(next(tmp_path.glob("*.jsonl")).read_text().splitlines()) == 3


def test_non_auth_alerts_are_opt_in(monkeypatch, tmp_path):
    client, _ = setup_run(monkeypatch, tmp_path)
    def fail(*args):
        raise RuntimeError("unrecognized response")
    monkeypatch.setattr(client, "fetch_page", fail)
    monkeypatch.setattr(exporter, "notify_export_failure", lambda **kw: pytest.fail("unexpected alert"))
    assert exporter.main() == 1


def test_exhausted_blank_response_keeps_page_incomplete_and_reports_safe_metadata(monkeypatch, tmp_path, capsys):
    client, args = setup_run(monkeypatch, tmp_path)
    original = client.fetch_page
    response = requests.Response()
    response.status_code = 200
    response._content = b"\r\n"
    failure = CourtResponseError("blank_response", response)
    failure.attempts = 3
    def fetch(self, filters, page):
        if page == 2:
            raise failure
        return original(self, filters, page)
    monkeypatch.setattr(client, "fetch_page", fetch)
    monkeypatch.setattr(exporter, "telegram_configured", lambda: True)
    alerts = []
    monkeypatch.setattr(exporter, "notify_export_failure", lambda **kwargs: alerts.append(kwargs) or True)
    monkeypatch.setattr(sys, "argv", args + ["--notify-telegram"])
    assert exporter.main() == 1
    state = json.loads(next(tmp_path.glob("*.state.json")).read_text())
    assert state["completed_pages"] == {"151": [1, 3]}
    assert state["pending_pages"]["151"]["2"]["reason"] == "blank_response"
    assert not list(tmp_path.glob("*.jsonl"))
    assert alerts == [{"court_id": 151, "type_proc": 14, "page": 2,
                       "unique_total": 2, "error_type": "CourtResponseError",
                       "pages_completed": 2, "pages_total": 3,
                       "current_pages_completed": 2, "current_pages_total": 3,
                       "reason": "blank_response", "http_status": 200,
                       "response_bytes": 2, "attempts": 3}]
    assert '"reason": "blank_response"' in capsys.readouterr().err
    client.calls.clear()
    monkeypatch.setattr(client, "fetch_page", original)
    assert exporter.main() == 0
    assert client.calls == [2]
    rows = [json.loads(line) for line in next(tmp_path.glob("*.jsonl")).read_text().splitlines()]
    assert {row["key"] for row in rows} == {"document:1", "document:2", "document:3"}


@pytest.mark.parametrize("reason", ["unexpected_redirect", "unrecognized_response"])
def test_redirect_and_unknown_responses_still_stop_before_next_page(monkeypatch, tmp_path, reason):
    client, _ = setup_run(monkeypatch, tmp_path)
    response = requests.Response()
    response.status_code = 302 if reason == "unexpected_redirect" else 200
    original = client.fetch_page

    def fetch(self, filters, page):
        if page == 2:
            raise CourtResponseError(reason, response)
        return original(self, filters, page)

    monkeypatch.setattr(client, "fetch_page", fetch)
    assert exporter.main() == 1
    state = json.loads(next(tmp_path.glob("*.state.json")).read_text())
    assert state["completed_pages"] == {"151": [1]}
    assert not state.get("pending_pages")
    assert 3 not in client.calls


def test_three_consecutive_blank_pages_stop_and_preserve_all_gaps(monkeypatch, tmp_path):
    client, _ = setup_run(monkeypatch, tmp_path)
    response = requests.Response()
    response.status_code = 200
    response._content = b"\r\n"

    def fetch(self, filters, page):
        self.calls.append(page)
        if page > 1:
            raise CourtResponseError("blank_response", response)
        return [record(page)], 8

    monkeypatch.setattr(client, "fetch_page", fetch)
    assert exporter.main() == 1
    assert client.calls == [1, 2, 3, 4]
    state = json.loads(next(tmp_path.glob("*.state.json")).read_text())
    assert set(state["pending_pages"]["151"]) == {"2", "3", "4"}
    assert state["completed_pages"] == {"151": [1]}


def test_auth_notification_is_managed_by_controller_when_heartbeat_is_fresh(monkeypatch, tmp_path):
    client, args = setup_run(monkeypatch, tmp_path)
    client.fail = 2
    monkeypatch.setattr(exporter, "telegram_configured", lambda: True)
    monkeypatch.setattr(exporter, "notifications_managed", lambda _: True)
    monkeypatch.setattr(exporter, "notify_auth_failure", lambda **kw: pytest.fail("Duplicate auth alert"))
    monkeypatch.setattr(sys, "argv", args + ["--notify-telegram"])
    assert exporter.main() == 2
    state = json.loads(next(tmp_path.glob("*.state.json")).read_text())
    assert state["completed_pages"] == {"151": [1]}
