"""Celery: периодический синк резидентов СЭЗ (ЕАЭС, portal.eaeunion.org)."""
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logger import get_logger
from app.services.eaeu_sez import sync_eaeu_sez_residents
from app.services.source_fetch_state import record_source_health
from app.tasks.celery_app import celery_app

logger = get_logger("tasks.eaeu_sez")


@celery_app.task(
    bind=True,
    name="app.tasks.eaeu_sez_tasks.sync_eaeu_sez_residents",
    time_limit=7200,
    soft_time_limit=7000,
)
def sync_eaeu_sez_residents_task(self, country: str | None = None, limit_pages: int | None = None) -> dict:
    """Выгрузить реестр СЭЗ (пагинация) и обновить записи апсёртом (без удаления)."""
    db = SessionLocal()
    try:
        stats = sync_eaeu_sez_residents(
            db,
            country=country or settings.SEZ_COUNTRY,
            limit_pages=limit_pages,
        )
        record_source_health(db, "eaeu_sez", stats)
        if stats["status"] == "source_unavailable":
            raise RuntimeError(f"EAEU SEZ source unavailable; database preserved: {stats['source_error']}")
        logger.info("EAEU SEZ sync finished: %s", stats)
        return stats
    finally:
        db.close()
