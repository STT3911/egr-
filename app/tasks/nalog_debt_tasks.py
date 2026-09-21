"""Celery-задача синхронизации налоговой задолженности (portal.nalog.gov.by).

Портал отдаёт данные через GWT-RPC. Задача обновляет текущий срез либо
непосредственно предыдущий месяц, если текущий пуст. Пустые ответы и ошибки
не перезаписывают хорошие файлы/данные; состояние источника сохраняется отдельно.

Включается флагом NALOG_DEBT_SCHEDULE_ENABLED, идёт в очередь heavy.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logger import get_logger
from app.services.nalog_debt import refresh_latest_debt_slice
from app.services.source_fetch_state import record_source_health
from app.tasks.celery_app import celery_app

logger = get_logger("tasks.nalog_debt")


@celery_app.task(
    bind=True,
    name="app.tasks.nalog_debt_tasks.sync_nalog_debt",
    time_limit=7200,
    soft_time_limit=7080,
)
def sync_nalog_debt_task(self, out_dir: Optional[str] = None) -> Dict[str, Any]:
    """Обновить доступный срез и вернуть его дату, объём и статус источника."""
    target_dir = Path(out_dir or settings.NALOG_DEBT_OUT_DIR)
    logger.info("Nalog debt sync started (monthly), out_dir=%s", target_dir)

    db = SessionLocal()
    try:
        result = refresh_latest_debt_slice(db, target_dir)
        record_source_health(db, "nalog_debt", result)
    except Exception as exc:
        db.rollback()
        record_source_health(db, "nalog_debt", {"status": "failed", "error_type": type(exc).__name__})
        raise
    finally:
        db.close()

    log = logger.info if result["status"] == "success" else logger.warning
    log("Nalog debt sync finished: %s", result)
    return {**result, "out_dir": str(target_dir)}
