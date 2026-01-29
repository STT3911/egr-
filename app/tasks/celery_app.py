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

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone="Europe/Minsk",
    enable_utc=True,
    beat_schedule={
        # Historical data load (1900 to today) - runs once per week on Sunday at 1 AM
        "auto-fetch-historical": {
            "task": "app.tasks.sync_tasks.auto_fetch_historical_data",
            "schedule": crontab(day_of_week=0, hour=1, minute=0),  # Sunday 1 AM
            "args": (1900, 60),  # From 1900, 60 months (5 years) per period
        },
        # Auto-fetch from API to JSON, then load to DB (every 6 hours)
        "auto-fetch-and-load-recent": {
            "task": "app.tasks.sync_tasks.auto_fetch_recent_to_json_and_db",
            "schedule": crontab(hour="*/6"),  # Every 6 hours
            "args": (),
        },
        # Process any pending raw data every 30 seconds
        "process-pending-raw": {
            "task": "app.tasks.sync_tasks.process_pending_raw",
            "schedule": timedelta(seconds=30),
            "args": (2000,),  # 2000 records per batch
        },
        # Load existing JSON files (if any) every night at 2 AM
        "load-from-json": {
            "task": "app.tasks.sync_tasks.load_companies_from_json",
            "schedule": crontab(hour=2, minute=0),
            "args": (True,),  # auto_process=True
        },
        # Sync daily changes (backup method) at 3 AM
        "sync-daily-changes": {
            "task": "app.tasks.sync_tasks.sync_daily_changes",
            "schedule": crontab(hour=3, minute=0),
            "args": (),
        },
        # Update reference tables at 4 AM
        "update-reference-tables": {
            "task": "app.tasks.sync_tasks.update_reference_tables",
            "schedule": crontab(hour=4, minute=0),
            "args": (),
        },
        # Fetch GRP (налоговая) data for companies (daily, only missing)
        "sync-grp-missing": {
            "task": "app.tasks.sync_tasks.sync_grp_for_all",
            "schedule": crontab(hour=5, minute=0),
            "args": (),
            "kwargs": {"limit": 5000, "only_missing": True},
        },
        # Reprocess failed rows on Saturday at 5 AM
        "reprocess-failed-rows": {
            "task": "app.tasks.sync_tasks.reprocess_failed_rows",
            "schedule": crontab(day_of_week=6, hour=5, minute=0),
            "args": (),
        },
    }
)


