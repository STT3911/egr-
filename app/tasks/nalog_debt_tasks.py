"""Celery-задача синхронизации налоговой задолженности (portal.nalog.gov.by).

Портал отдаёт данные через GWT-RPC, поэтому задача повторяет то, что раньше
запускалось руками через scripts/run_nalog_debt.py:
  1. run_fetcher(mode="monthly") — тянет текущий месяц в JSON (permutation
     резолвится автоматически);
  2. run_import_to_db — грузит JSON в nalog_debt_records; там же эмитятся
     события EVENT_TAX_DEBT для новых должников (см. nalog_debt.load_json_file_to_db).

Включается флагом NALOG_DEBT_SCHEDULE_ENABLED, идёт в очередь heavy.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logger import get_logger
from app.services.nalog_debt import run_fetcher, run_import_to_db
from app.tasks.celery_app import celery_app

logger = get_logger("tasks.nalog_debt")


@celery_app.task(
    bind=True,
    name="app.tasks.nalog_debt_tasks.sync_nalog_debt",
    time_limit=7200,
    soft_time_limit=7080,
)
def sync_nalog_debt_task(self, out_dir: Optional[str] = None) -> Dict[str, Any]:
    """Скачать задолженность за текущий месяц и загрузить в БД.

    Returns:
        dict: {"imported": <кол-во записей>, "out_dir": <путь>}.
    """
    target_dir = Path(out_dir or settings.NALOG_DEBT_OUT_DIR)
    logger.info("Nalog debt sync started (monthly), out_dir=%s", target_dir)

    run_fetcher(mode="monthly", out_dir=target_dir, perm=None, overwrite=True)

    db = SessionLocal()
    try:
        imported = run_import_to_db(
            target_dir,
            db,
            latest_only=True,
            replace_existing_slice=True,
            raise_on_error=True,
        )
    finally:
        db.close()

    logger.info("Nalog debt sync finished: imported=%s", imported)
    return {"imported": imported, "out_dir": str(target_dir)}
