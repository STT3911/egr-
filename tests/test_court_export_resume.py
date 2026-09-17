"""Exercise resumable export without contacting the court service."""
import json
import sys

import pytest

from app.services.court_judgments import CourtAuthenticationError, CourtJudgment
from scripts import export_court_judgments as exporter


def test_cli_defaults_match_five_minute_client_delay(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["export_court_judgments.py", "--cookie-stdin"])
    args = exporter.parse_args()
    with exporter.CourtJudgmentClient("a=b") as client:
        assert args.delay == client.min_interval_seconds == 300
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
    assert alerts == [{"court_id": 151, "type_proc": 14, "unique_total": 1}]
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
