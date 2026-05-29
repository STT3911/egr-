"""Celery tasks for lightweight license.gov.by change checks."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.database import SessionLocal
from app.core.logger import get_logger
from app.database.models import LicenseSyncRun
from app.services.licenses import check_license_api_changes
from app.tasks.celery_app import celery_app

logger = get_logger("tasks.licenses")


@celery_app.task(
    bind=True,
    name="app.tasks.license_tasks.check_license_changes",
    time_limit=3600,
    soft_time_limit=3540,
)
def check_license_changes_task(
    self,
    pages: int = 1,
    page_size: int | None = None,
    verify_tls: bool | None = None,
) -> dict[str, Any]:
    """Check recent license.gov.by pages and upsert new or changed records."""
    db = SessionLocal()
    run = LicenseSyncRun(status="running")
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        stats = check_license_api_changes(
            db,
            pages=pages,
            page_size=page_size,
            verify_tls=verify_tls,
        )
        run.status = "success"
        run.finished_at = datetime.utcnow()
        run.total_records = int(stats.get("total", 0))
        run.processed_records = int(stats.get("saved", 0))
        run.created_count = int(stats.get("created", 0))
        run.updated_count = int(stats.get("updated", 0))
        run.unchanged_count = int(stats.get("unchanged", 0))
        run.failed_count = int(stats.get("invalid", 0))
        run.last_page = max(1, pages)
        run.stats_json = stats
        db.add(run)
        db.commit()
        logger.info("License change check finished: %s", stats)
        return {"run_id": str(run.id), **stats}
    except Exception as exc:
        db.rollback()
        run.status = "failed"
        run.finished_at = datetime.utcnow()
        run.error = str(exc)
        db.add(run)
        db.commit()
        raise
    finally:
        db.close()
