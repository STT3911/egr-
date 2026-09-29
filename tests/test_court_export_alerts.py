from types import SimpleNamespace

import pytest
import requests

from app.services import court_export_alerts as alerts


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("ALERT_TELEGRAM_BOT_TOKEN", "test-bot-secret")
    monkeypatch.setenv("ALERT_TELEGRAM_CHAT_ID", "123")


def send():
    return alerts.notify_auth_failure(court_id=151, type_proc=14, unique_total=110)


def test_unconfigured_does_not_contact_telegram(monkeypatch):
    monkeypatch.delenv("ALERT_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("ALERT_TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(alerts.requests, "post", lambda *a, **kw: pytest.fail("No network expected"))
    assert send() is False


def test_explicit_alert_independent_of_disabled_celery_alerts(configured, monkeypatch):
    monkeypatch.setenv("PARSER_ALERTS_ENABLED", "false")
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(status_code=200, json=lambda: {"ok": True})
    monkeypatch.setattr(alerts.requests, "post", post)
    assert send() is True
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url == "https://api.telegram.org/bottest-bot-secret/sendMessage"
    assert kwargs["timeout"] == 8
    assert kwargs["allow_redirects"] is False
    assert kwargs["json"]["chat_id"] == "123"
    text = kwargs["json"]["text"]
    assert "110" in text and "151" in text and "TypeProc: 14" in text
    assert "test-bot-secret" not in text


@pytest.mark.parametrize("status, ok", [(400, False), (302, True), (200, False)])
def test_failed_delivery_is_not_reported_as_success(configured, monkeypatch, status, ok):
    monkeypatch.setattr(alerts.requests, "post", lambda *a, **kw:
        SimpleNamespace(status_code=status, json=lambda: {"ok": ok}))
    assert send() is False


def test_delivery_exception_does_not_leak_token_or_retry(configured, monkeypatch, capsys):
    calls = []
    def post(*args, **kwargs):
        calls.append(args)
        raise requests.Timeout("https://api.telegram.org/bottest-bot-secret/sendMessage")
    monkeypatch.setattr(alerts.requests, "post", post)
    assert send() is False
    assert len(calls) == 1
    assert "test-bot-secret" not in capsys.readouterr().err


def test_generic_failure_alert_sanitizes_unknown_exception_labels(configured, monkeypatch):
    calls = []
    monkeypatch.setattr(alerts.requests, "post", lambda *a, **kw:
        calls.append(kw) or SimpleNamespace(status_code=200, json=lambda: {"ok": True}))
    assert alerts.notify_export_failure(court_id=151, type_proc=14, page=25,
        unique_total=310, error_type="secret-cookie-value")
    message = calls[0]["json"]["text"]
    assert "25" in message and "310" in message
    assert "ExportError" in message and "secret-cookie-value" not in message
