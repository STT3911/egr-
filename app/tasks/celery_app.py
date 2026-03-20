"""Celery application configuration"""
from celery import Celery
from celery.schedules import crontab
from datetime import timedelta
from app.core.config import settings

celery_app = Celery(
    "egr_aggregator",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.sync_tasks"]
)

# Импортируем модуль с задачами для регистрации
from app.tasks import sync_tasks

# Базовое расписание: EGR всегда в расписании, GRP — только если GRP_SCHEDULE_ENABLED
_beat_schedule = {
    # ----- EGR: fetch (API → raw) и process (raw → таблицы) -----
    "egr-fetch-raw": {
        "task": "app.tasks.sync_tasks.egr_fetch_raw",
        "schedule": timedelta(seconds=60),
        "args": (500,),
    },
    "egr-process-raw": {
        "task": "app.tasks.sync_tasks.egr_process_raw",
        "schedule": timedelta(seconds=20),
        "args": (1000,),
    },
    # ----- Остальные задачи (периодические) -----
    "auto-fetch-historical": {
        "task": "app.tasks.sync_tasks.auto_fetch_historical_data",
        "schedule": crontab(day_of_week=0, hour=1, minute=0),
        "args": (1900, 60),
    },
    "load-from-json": {
        "task": "app.tasks.sync_tasks.load_companies_from_json",
        "schedule": crontab(hour=2, minute=0),
        "args": (True,),
    },
    "sync-daily-changes": {
        "task": "app.tasks.sync_tasks.sync_daily_changes",
        "schedule": crontab(hour=3, minute=0),
        "args": (),
    },
    "update-reference-tables": {
        "task": "app.tasks.sync_tasks.update_reference_tables",
        "schedule": crontab(hour=4, minute=0),
        "args": (),
    },
    "reprocess-failed-rows": {
        "task": "app.tasks.sync_tasks.reprocess_failed_rows",
        "schedule": crontab(day_of_week=6, hour=5, minute=0),
        "args": (),
    },
}

# GRP в расписании только если включено (по умолчанию — ручной запуск)
if settings.GRP_SCHEDULE_ENABLED:
    _beat_schedule["grp-fetch-raw"] = {
        "task": "app.tasks.sync_tasks.grp_fetch_raw",
        "schedule": timedelta(seconds=120),
        "args": (300,),
    }
    _beat_schedule["grp-process-raw"] = {
        "task": "app.tasks.sync_tasks.grp_process_raw",
        "schedule": timedelta(seconds=30),
        "args": (500,),
    }

# Ежемесячный экспорт GRP в JSON — всегда в расписании
_beat_schedule["grp-monthly-export"] = {
    "task": "app.tasks.sync_tasks.grp_monthly_export",
    "schedule": crontab(day_of_month=1, hour=6, minute=0),  # 1-го числа каждого месяца в 06:00
    "args": (),
}

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone="Europe/Minsk",
    enable_utc=True,
    beat_schedule=_beat_schedule,
)


