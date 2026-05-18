"""Celery tasks for trade registry imports."""

from __future__ import annotations

from app.core.logger import get_logger
from app.services.trade_registry_import import run_admin_trade_registry_import
from app.tasks.celery_app import celery_app

logger = get_logger("tasks.trade_registry")


@celery_app.task(bind=True, name="app.tasks.trade_registry_tasks.import_trade_registry_csv", time_limit=14400, soft_time_limit=14340)
def import_trade_registry_csv_task(self, run_id: str) -> dict:
    logger.info("Starting trade registry import run %s", run_id)
    return run_admin_trade_registry_import(run_id)
