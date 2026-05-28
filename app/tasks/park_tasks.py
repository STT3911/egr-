"""Celery tasks for syncing park.by HTP/PVT residents."""

from __future__ import annotations

from pathlib import Path

from app.core.database import SessionLocal
from app.core.logger import get_logger

from app.services.park_residents import sync_pvt_residents, sync_pvt_residents_from_catalog
from app.tasks.celery_app import celery_app

logger = get_logger("tasks.park")


@celery_app.task(bind=True, name="app.tasks.park_tasks.sync_pvt_residents", time_limit=86400, soft_time_limit=85800)
def sync_pvt_residents_task(
    self,
    limit: int | None = None,
    offset: int = 0,
    start_unp: int | None = None,
    batch_size: int = 100,
    delay: float = 0.2,
    timeout: float = 30.0,
    only_missing: bool = False,
    proxy: str | None = None,
    resume: bool = True,
    source: str = "catalog",
    output: str | None = None,
    letters: str | None = None,
    prefixes: str | None = None,
) -> dict[str, int]:
    db = SessionLocal()
    try:
        if source == "catalog":
            stats = sync_pvt_residents_from_catalog(
                db,
                output=Path(output) if output else None,
                letters=list(prefixes or letters) if (prefixes or letters) else None,
                limit=limit,
                batch_size=batch_size,
                delay=delay,
                timeout=timeout,
                proxy=proxy,
            )
        else:
            stats = sync_pvt_residents(
                db,
                limit=limit,
                offset=offset,
                start_unp=start_unp,
                batch_size=batch_size,
                delay=delay,
                timeout=timeout,
                only_missing=only_missing,
                proxy=proxy,
                resume=resume,
            )
        logger.info("PVT residents sync finished: %s", stats)
        return stats
    finally:
        db.close()
