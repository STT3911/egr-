"""Celery tasks for syncing bankrot.gov.by bankruptcy cases."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.database import SessionLocal
from app.core.logger import get_logger
from app.services.bankrot_sync import sync_bankrot_cases
from app.tasks.celery_app import celery_app

logger = get_logger("tasks.bankrot")


@celery_app.task(
    bind=True,
    name="app.tasks.bankrot_tasks.sync_bankrot_cases",
    time_limit=86400,
    soft_time_limit=85800,
)
def sync_bankrot_cases_task(
    self,
    page_size: Optional[int] = None,
    delay: Optional[float] = None,
    detail_delay: Optional[float] = None,
    output_dir: Optional[str] = None,
    save_every: Optional[int] = None,
    token: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    fetch_related_data: Optional[bool] = None,
    related_datasets: Optional[list[str]] = None,
) -> Dict[str, int]:
    """Запустить полную синхронизацию bankrot.gov.by.

    Все параметры необязательны — без них используются значения из .env
    (BANKROT_PAGE_SIZE, BANKROT_PAGE_DELAY_SECONDS и т.д.).

    Returns:
        dict со счётчиками: processed, failed, upserted, no_unp.
    """
    db = SessionLocal()
    try:
        stats = sync_bankrot_cases(
            db,
            page_size=page_size,
            delay=delay,
            detail_delay=detail_delay,
            output_dir=output_dir,
            save_every=save_every,
            token=token,
            filters=filters,
            fetch_related_data=fetch_related_data,
            related_datasets=related_datasets,
        )
        logger.info("Bankrot sync task finished: %s", stats)
        return stats
    finally:
        db.close()
