"""Celery: периодическая пересборка ключей текущих адресов компаний."""
from app.core.database import SessionLocal
from app.core.logger import get_logger
from app.services.company_addresses import rebuild_company_address_keys
from app.tasks.celery_app import celery_app

logger = get_logger("tasks.addresses")


@celery_app.task(name="app.tasks.address_tasks.rebuild_company_address_keys_task")
def rebuild_company_address_keys_task():
    """Полная идемпотентная пересборка company_address_keys из текущих адресов ЕГР.

    Используется и как разовый бэкфилл (запустить один раз), и как ежедневная задача.
    """
    db = SessionLocal()
    try:
        return rebuild_company_address_keys(db)
    finally:
        db.close()
