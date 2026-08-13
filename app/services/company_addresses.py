"""Сборка `company_address_keys`: нормализованный ключ ТЕКУЩЕГО адреса компании.

Идемпотентно: одна строка на компанию (upsert по company_id), устаревшие (компания
не встретилась в этом прогоне — адрес пропал/не распарсился) — удаляются.
"Текущий" адрес — тот же критерий, что и везде в кодовой базе (см. admin.py):
valid_to IS NULL в приоритете, иначе последний valid_from.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.logger import get_logger
from app.database.models import CompanyAddressKey
from app.utils.address_key import building_address_key, unit_address_key

logger = get_logger("company_addresses")

_BATCH = 2000
_LOCK_KEY = 911003   # отдельный ключ advisory-lock (911002 занят company_contacts)

_CURRENT_ADDRESS_SQL = text(
    """
    SELECT DISTINCT ON (a.company_id)
        a.company_id, c.unp, a.full_address
    FROM egr_company_addresses_history a
    JOIN egr_companies c ON c.id = a.company_id
    ORDER BY a.company_id, (a.valid_to IS NULL) DESC, a.valid_to DESC NULLS LAST, a.valid_from DESC NULLS LAST
    """
)


def rebuild_company_address_keys(db: Session) -> dict:
    """Полная идемпотентная пересборка ключей текущих адресов.

    Защищена advisory-lock (как rebuild_company_contacts) — два параллельных
    прогона невозможны (иначе дедлоки на конкурентных upsert).
    """
    got = db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _LOCK_KEY}).scalar()
    if not got:
        logger.warning("rebuild_company_address_keys: уже выполняется в другом процессе — пропуск")
        return {"skipped": True}

    run_started = datetime.utcnow()
    batch: list[dict] = []
    upserted = 0
    skipped_no_key = 0

    def flush():
        nonlocal upserted
        if not batch:
            return
        stmt = pg_insert(CompanyAddressKey).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=[CompanyAddressKey.company_id],
            set_={
                "unp": stmt.excluded.unp,
                "full_address": stmt.excluded.full_address,
                "address_key": stmt.excluded.address_key,
                "unit_address_key": stmt.excluded.unit_address_key,
                "last_seen_at": run_started,
            },
        )
        db.execute(stmt)
        db.commit()              # покоммитно — без гигантской транзакции
        upserted += len(batch)
        batch.clear()

    # Отдельная read-сессия со streaming (таблица адресов большая) — писать через db.
    read_db = SessionLocal()
    try:
        rows = read_db.execute(
            _CURRENT_ADDRESS_SQL,
            execution_options={"stream_results": True, "yield_per": _BATCH},
        )
        for company_id, unp, full_address in rows:
            key = building_address_key(full_address)
            if key is None:
                skipped_no_key += 1
                continue
            batch.append({
                "company_id": company_id, "unp": unp,
                "full_address": full_address,
                "address_key": key,
                "unit_address_key": unit_address_key(full_address),
                "last_seen_at": run_started,
            })
            if len(batch) >= _BATCH:
                flush()
        flush()

        # Компании без текущего адреса/с нераспознанным адресом — удаляем устаревшую запись.
        pruned = db.execute(
            delete(CompanyAddressKey).where(CompanyAddressKey.last_seen_at < run_started)
        ).rowcount
        db.commit()
    finally:
        read_db.close()
        db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_KEY})
        db.commit()

    logger.info(
        "company_address_keys rebuilt: upserted=%s pruned=%s skipped_no_key=%s",
        upserted, pruned, skipped_no_key,
    )
    return {"upserted": upserted, "pruned": pruned, "skipped_no_key": skipped_no_key}
