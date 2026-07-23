"""Global Telegram monitoring for parser-related Celery tasks."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from celery.signals import task_failure, task_postrun, task_prerun, task_retry

from app.core.config import settings
from app.services.telegram_alerts import send_telegram_alert

logger = logging.getLogger("egr_aggregator.parser_alerts")

_PARSER_TASK_PREFIXES = (
    "app.tasks.sync_tasks.",
    "app.tasks.trade_registry_tasks.",
    "app.tasks.park_tasks.",
    "app.tasks.bankrot_tasks.",
    "app.tasks.license_tasks.",
    "app.tasks.contacts_tasks.",
    "app.tasks.eaeu_sez_tasks.",
    "app.tasks.address_tasks.",
    "app.tasks.nalog_debt_tasks.",
)

_EXCLUDED_TASKS = {
    "app.tasks.sync_tasks.sync_specific_company",
    "app.tasks.sync_tasks.egr_fetch_raw_one",
    "app.tasks.sync_tasks.process_period_range",
    "app.tasks.sync_tasks.fetch_period_to_json",
    "app.tasks.sync_tasks.process_search_index_queue",
}

_started_at: dict[str, float] = {}


def is_parser_task(task_name: str | None) -> bool:
    if not task_name or task_name in _EXCLUDED_TASKS:
        return False
    return task_name.startswith(_PARSER_TASK_PREFIXES)


def _task_name(sender: Any = None, task: Any = None, request: Any = None) -> str:
    for candidate in (sender, task):
        name = getattr(candidate, "name", None)
        if name:
            return str(name)
    request_name = getattr(request, "task", None)
    return str(request_name or "")


def _display_name(task_name: str) -> str:
    return task_name.rsplit(".", 1)[-1]


def _duration(task_id: str | None) -> float | None:
    if not task_id:
        return None
    started_at = _started_at.pop(task_id, None)
    if started_at is None:
        return None
    return max(0.0, time.monotonic() - started_at)


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "неизвестно"
    if seconds < 60:
        return f"{seconds:.1f} сек"
    minutes, remainder = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes} мин {remainder} сек"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} ч {minutes} мин"


def _format_result(result: Any) -> str:
    try:
        if isinstance(result, str):
            rendered = result
        else:
            rendered = json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        rendered = repr(result)
    limit = max(100, settings.PARSER_ALERTS_RESULT_MAX_CHARS)
    return rendered if len(rendered) <= limit else f"{rendered[:limit]}…"


@task_prerun.connect
def parser_task_started(
    sender=None,
    task_id=None,
    task=None,
    **kwargs,
) -> None:
    task_name = _task_name(sender=sender, task=task)
    if not is_parser_task(task_name):
        return
    if task_id:
        _started_at[str(task_id)] = time.monotonic()
    if settings.PARSER_ALERTS_NOTIFY_START:
        send_telegram_alert(
            "▶️ Парсер запущен\n"
            f"Задача: {_display_name(task_name)}\n"
            f"ID: {task_id or '-'}"
        )


@task_postrun.connect
def parser_task_finished(
    sender=None,
    task_id=None,
    task=None,
    retval=None,
    state=None,
    **kwargs,
) -> None:
    task_name = _task_name(sender=sender, task=task)
    if not is_parser_task(task_name):
        return
    elapsed = _duration(str(task_id) if task_id else None)
    if state != "SUCCESS" or not settings.PARSER_ALERTS_NOTIFY_SUCCESS:
        return
    send_telegram_alert(
        "✅ Парсер завершён\n"
        f"Задача: {_display_name(task_name)}\n"
        f"Время: {_format_duration(elapsed)}\n"
        f"Результат: {_format_result(retval)}"
    )


@task_retry.connect
def parser_task_retried(
    sender=None,
    request=None,
    reason=None,
    **kwargs,
) -> None:
    task_name = _task_name(sender=sender, request=request)
    if not is_parser_task(task_name):
        return
    send_telegram_alert(
        "🔁 Парсер отправлен на повтор\n"
        f"Задача: {_display_name(task_name)}\n"
        f"ID: {getattr(request, 'id', '-')}\n"
        f"Причина: {str(reason)[:1000]}"
    )


@task_failure.connect
def parser_task_failed(
    sender=None,
    task_id=None,
    exception=None,
    **kwargs,
) -> None:
    task_name = _task_name(sender=sender)
    if not is_parser_task(task_name):
        return
    elapsed = _duration(str(task_id) if task_id else None)
    send_telegram_alert(
        "❌ Парсер завершился с ошибкой\n"
        f"Задача: {_display_name(task_name)}\n"
        f"ID: {task_id or '-'}\n"
        f"Время: {_format_duration(elapsed)}\n"
        f"Ошибка: {type(exception).__name__}: {str(exception)[:1500]}"
    )
