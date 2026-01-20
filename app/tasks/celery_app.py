"""Celery application configuration"""
from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "egr_aggregator",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.sync_tasks"]
)

# Импортируем модуль с задачами для регистрации
from app.tasks import sync_tasks

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone="Europe/Minsk",
    enable_utc=True,
    beat_schedule={
        "sync-daily-changes": {
            "task": "app.tasks.sync_tasks.sync_daily_changes",
            "schedule": crontab(hour=3, minute=0),
            "args": (),
        },
        "reprocess-failed-rows": {
            "task": "app.tasks.sync_tasks.reprocess_failed_rows",
            "schedule": crontab(day_of_week=6, hour=5, minute=0),
            "args": (),
        },
        "update-reference-tables": {
            "task": "app.tasks.sync_tasks.update_reference_tables",
            "schedule": crontab(hour=4, minute=0),  # Каждый день в 4:00
            "args": (),
        },
        "load-from-json": {
            "task": "app.tasks.sync_tasks.load_companies_from_json",
            "schedule": crontab(hour=2, minute=0),
            "args": (),
        },
    }
)


