"""Celery application configuration"""
from celery import Celery
from celery.schedules import crontab
from datetime import timedelta
from app.core.config import settings

celery_app = Celery(
    "egr_aggregator",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.sync_tasks", "app.tasks.trade_registry_tasks", "app.tasks.park_tasks"]
)

# Импортируем модуль с задачами для регистрации
from app.tasks import sync_tasks
from app.tasks import trade_registry_tasks
from app.tasks import park_tasks

# Базовое расписание: EGR всегда в расписании, GRP — только если GRP_SCHEDULE_ENABLED
_beat_schedule = {
    # ----- EGR: fetch (API → raw) и process (raw → таблицы) -----
    "egr-fetch-raw": {
        "task": "app.tasks.sync_tasks.egr_fetch_raw",
        "schedule": crontab(hour="0,12", minute=30),
        "args": (500,),
    },
    "egr-process-raw": {
        "task": "app.tasks.sync_tasks.egr_process_raw",
        "schedule": crontab(hour="1,13", minute=30),
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
    "gias-sync-directory-registries": {
        "task": "app.tasks.sync_tasks.sync_gias_directory_registries",
        "schedule": crontab(hour=4, minute=30),
        "args": (),
    },

    "egr-sync-place-locations": {
        "task": "app.tasks.sync_tasks.egr_sync_place_locations",
        "schedule": crontab(hour="2,14", minute=30),
        "args": (500, 20),
    },
    "reprocess-failed-rows": {
        "task": "app.tasks.sync_tasks.reprocess_failed_rows",
        "schedule": crontab(day_of_week=6, hour=5, minute=0),
        "args": (),
    },
    "process-search-index-queue": {
        "task": "app.tasks.sync_tasks.process_search_index_queue",
        "schedule": timedelta(seconds=settings.ELASTICSEARCH_QUEUE_SCHEDULE_SECONDS),
        "args": (settings.ELASTICSEARCH_QUEUE_BATCH_SIZE,),
    },
}

# GRP в расписании только если включено (по умолчанию — ручной запуск)
if settings.GRP_SCHEDULE_ENABLED:
    _beat_schedule["grp-fetch-raw"] = {
        "task": "app.tasks.sync_tasks.grp_fetch_raw",
        "schedule": timedelta(seconds=settings.GRP_FETCH_SCHEDULE_SECONDS),
        "args": (settings.GRP_FETCH_LIMIT, settings.GRP_FETCH_BATCH_SIZE),
    }
    _beat_schedule["grp-process-raw"] = {
        "task": "app.tasks.sync_tasks.grp_process_raw",
        "schedule": timedelta(seconds=settings.GRP_PROCESS_SCHEDULE_SECONDS),
        "args": (settings.GRP_PROCESS_LIMIT,),
    }

# Ежемесячный экспорт GRP в JSON — всегда в расписании
_beat_schedule["grp-monthly-export"] = {
    "task": "app.tasks.sync_tasks.grp_monthly_export",
    "schedule": crontab(day_of_month=1, hour=6, minute=0),  # 1-го числа каждого месяца в 06:00
    "args": (),
}

if not settings.GIAS_SYNC_ENABLED:
    _beat_schedule.pop("gias-sync-directory-registries", None)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone="Europe/Minsk",
    enable_utc=True,
    beat_schedule=_beat_schedule,
)
