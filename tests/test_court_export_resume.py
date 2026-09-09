"""Exercise resumable export without contacting the court service."""
import json
import sys

from app.services.court_judgments import CourtAuthenticationError, CourtJudgment
from scripts import export_court_judgments as exporter


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
