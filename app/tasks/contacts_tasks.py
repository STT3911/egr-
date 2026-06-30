"""Celery: периодическая пересборка агрегированных контактов компании."""
from app.core.database import SessionLocal
from app.core.logger import get_logger
from app.services.company_contacts import rebuild_company_contacts
from app.tasks.celery_app import celery_app

logger = get_logger("tasks.contacts")


@celery_app.task(name="app.tasks.contacts_tasks.rebuild_company_contacts_task")
def rebuild_company_contacts_task():
    """Полная идемпотентная пересборка company_contacts из всех источников.

    Используется и как разовый бэкфилл (запустить один раз), и как ежедневная задача.
    """
    db = SessionLocal()
    try:
        return rebuild_company_contacts(db)
    finally:
        db.close()
