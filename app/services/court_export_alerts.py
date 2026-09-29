"""Opt-in alerts for the standalone exporter, without DB/Celery settings."""

from __future__ import annotations

import os
import sys

import requests


def telegram_configured() -> bool:
    return bool(
        os.environ.get("ALERT_TELEGRAM_BOT_TOKEN", "").strip()
        and os.environ.get("ALERT_TELEGRAM_CHAT_ID", "").strip()
    )


def notify_auth_failure(*, court_id: int, type_proc: int, unique_total: int) -> bool:
    """Send once; never include cookies, response bodies or exception details."""
    if not telegram_configured():
        return False
    text = (
        "⚠️ Выгрузка судов остановлена: сайт отклонил авторизацию.\n"
        "Куки могли истечь либо доступ аккаунта ограничен.\n"
        f"Суд: {court_id}; TypeProc: {type_proc}.\n"
        f"Уникальных записей в текущем файле: {unique_total}.\n"
        "Сохранённые страницы остаются в JSONL и checkpoint.\n"
        "Обновите court.cookie и возобновите контейнер выгрузки."
    )
    return _send(text)


def notify_export_failure(*, court_id: int, type_proc: int, page: int,
                          unique_total: int, error_type: str) -> bool:
    """Only allow known exception labels, never arbitrary diagnostic text."""
    if error_type not in {"RuntimeError", "ValueError", "OSError", "PermissionError",
                          "ConnectionError", "Timeout", "ReadTimeout", "ConnectTimeout",
                          "HTTPError", "RetryError"}:
        error_type = "ExportError"
    return _send(
        "❌ Выгрузка судов остановлена: ошибка ответа, сети или сохранения.\n"
        f"Суд: {court_id}; TypeProc: {type_proc}; страница: {page}.\n"
        f"Тип ошибки: {error_type}.\n"
        f"Уникальных записей в текущем файле: {unique_total}.\n"
        "Ранее сохранённый прогресс оставлен. Ошибочная страница не завершена.\n"
        "Нужна диагностика перед продолжением; это не обязательно истечение куки."
    )


def _send(text: str) -> bool:
    if not telegram_configured():
        return False
    try:
        response = requests.post(
            "https://api.telegram.org/bot"
            + os.environ["ALERT_TELEGRAM_BOT_TOKEN"].strip()
            + "/sendMessage",
            json={
                "chat_id": os.environ["ALERT_TELEGRAM_CHAT_ID"].strip(),
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=8,
            allow_redirects=False,
        )
        return response.status_code == 200 and response.json().get("ok") is True
    except Exception:
        # Exception strings may contain the URL with the bot token.
        print("Court Telegram notification failed; details suppressed", file=sys.stderr)
        return False
