"""Celery task for public Minsk leadership observations."""

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logger import get_logger
from app.services.minsk_leadership import sync_minsk_leadership
from app.tasks.celery_app import celery_app


logger = get_logger("tasks.minsk_leadership")


@celery_app.task(
    name="app.tasks.minsk_leadership_tasks.sync_minsk_leadership",
    time_limit=600,
    soft_time_limit=570,
)
def sync_minsk_leadership_task() -> dict:
    db = SessionLocal()
    try:
        result = sync_minsk_leadership(
            db,
            timeout=settings.MINSK_LEADERSHIP_TIMEOUT_SECONDS,
            retries=settings.MINSK_LEADERSHIP_RETRIES,
            delay=settings.MINSK_LEADERSHIP_REQUEST_DELAY_SECONDS,
        )
        logger.info("Minsk leadership sync finished: %s", result)
        return result
    finally:
        db.close()
