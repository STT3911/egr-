"""Opt-in alerts for the standalone exporter, without DB/Celery settings."""

from __future__ import annotations

import os
import sys
import json
import time
from pathlib import Path

import requests


def notifications_managed(cookie_file: Path | None) -> bool:
    if cookie_file is None:
        return False
    try:
        path = cookie_file.parent / ".court-control-heartbeat.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return 0 <= time.time() - float(data["updated_at"]) < 120
    except (OSError, ValueError, KeyError, TypeError):
        return False


def telegram_configured() -> bool:
    return bool(
        os.environ.get("ALERT_TELEGRAM_BOT_TOKEN", "").strip()
        and os.environ.get("ALERT_TELEGRAM_CHAT_ID", "").strip()
    )


def auth_chat_id(cookie_file: Path | None = None) -> str:
    """Separate auth destination; heartbeat metadata survives controller downtime."""
    configured = os.environ.get("COURT_AUTH_TELEGRAM_CHAT_ID", "").strip()
    if configured:
        return configured
    if cookie_file is not None:
        try:
            data = json.loads((cookie_file.parent / ".court-control-heartbeat.json").read_text(encoding="utf-8"))
            chat_id = data["auth_chat_id"]
            if isinstance(chat_id, int) and not isinstance(chat_id, bool) and chat_id != 0:
                return str(chat_id)
        except (OSError, ValueError, KeyError, TypeError):
            pass
    # Backwards compatibility for standalone runs without a cookie controller.
    return os.environ.get("ALERT_TELEGRAM_CHAT_ID", "").strip()


def _progress_lines(*, pages_completed: int | None, pages_total: int | None,
                    current_pages_completed: int | None,
                    current_pages_total: int | None, unique_total: int) -> str:
    lines = []
    if isinstance(pages_completed, int):
        total = f" из {pages_total}" if isinstance(pages_total, int) and pages_total > 0 else ""
        lines.append(f"Пропарсено страниц: {pages_completed}{total}.")
    if isinstance(current_pages_completed, int):
        current_total = (
            f" из {current_pages_total}"
            if isinstance(current_pages_total, int) and current_pages_total > 0
            else ""
        )
        lines.append(f"По текущему суду: {current_pages_completed}{current_total} страниц.")
    lines.append(f"Уникальных дел в текущем файле: {unique_total}.")
    return "\n".join(lines)


def notify_auth_failure(*, court_id: int, type_proc: int, unique_total: int,
                        page: int | None = None, pages_completed: int | None = None,
                        pages_total: int | None = None,
                        current_pages_completed: int | None = None,
                        current_pages_total: int | None = None,
                        cookie_file: Path | None = None) -> bool:
    """Send once; never include cookies, response bodies or exception details."""
    if not telegram_configured():
        return False
    text = (
        "⚠️ Выгрузка судов остановлена: сайт отклонил авторизацию.\n"
        "Куки могли истечь либо доступ аккаунта ограничен.\n"
        f"Суд: {court_id}; TypeProc: {type_proc}.\n"
        + (f"Ошибка на странице: {page}.\n" if isinstance(page, int) else "")
        + _progress_lines(
            pages_completed=pages_completed,
            pages_total=pages_total,
            current_pages_completed=current_pages_completed,
            current_pages_total=current_pages_total,
            unique_total=unique_total,
        ) + "\n"
        "Сохранённые страницы остаются в JSONL и checkpoint.\n"
        "Обновите court.cookie и возобновите контейнер выгрузки."
    )
    return _send(text, chat_id=auth_chat_id(cookie_file))


def notify_export_failure(*, court_id: int, type_proc: int, page: int,
                          unique_total: int, error_type: str, reason: str = "",
                          http_status: int | None = None, response_bytes: int | None = None,
                          attempts: int = 1, pages_completed: int | None = None,
                          pages_total: int | None = None,
                          current_pages_completed: int | None = None,
                          current_pages_total: int | None = None) -> bool:
    """Only allow known exception labels, never arbitrary diagnostic text."""
    if error_type not in {"RuntimeError", "ValueError", "OSError", "PermissionError",
                          "ConnectionError", "Timeout", "ReadTimeout", "ConnectTimeout",
                          "HTTPError", "RetryError", "CourtResponseError"}:
        error_type = "ExportError"
    explanations = {
        "blank_response": "Сайт вернул пустой HTTP 200; три попытки той же страницы не дали данных.",
        "unrecognized_response": "Сайт вернул ответ, который парсер не распознал.",
        "unexpected_redirect": "Сайт перенаправил запрос на неожиданный адрес.",
    }
    diagnostic = explanations.get(reason, "")
    if diagnostic and isinstance(http_status, int) and isinstance(response_bytes, int):
        diagnostic += f" HTTP: {http_status}; размер ответа: {response_bytes} байт."
    if diagnostic:
        diagnostic += "\n"
    return _send(
        "❌ Выгрузка судов остановлена: ошибка ответа, сети или сохранения.\n"
        + diagnostic +
        f"Суд: {court_id}; TypeProc: {type_proc}; страница: {page}.\n"
        f"Тип ошибки: {error_type}.\n"
        + _progress_lines(
            pages_completed=pages_completed,
            pages_total=pages_total,
            current_pages_completed=current_pages_completed,
            current_pages_total=current_pages_total,
            unique_total=unique_total,
        ) + "\n"
        "Ранее сохранённый прогресс оставлен. Ошибочная страница не завершена.\n"
        "Нужна диагностика перед продолжением; это не обязательно истечение куки."
    )


def _send(text: str, *, chat_id: str | None = None) -> bool:
    if not telegram_configured():
        return False
    try:
        response = requests.post(
            "https://api.telegram.org/bot"
            + os.environ["ALERT_TELEGRAM_BOT_TOKEN"].strip()
            + "/sendMessage",
            json={
                "chat_id": chat_id if chat_id is not None else os.environ["ALERT_TELEGRAM_CHAT_ID"].strip(),
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
