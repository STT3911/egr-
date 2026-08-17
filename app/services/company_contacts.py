"""Сборка агрегированной таблицы `company_contacts` из всех источников.

Идемпотентно: при каждом прогоне контакты из источников апсёртятся (обновляется
last_seen_at), а устаревшие авто-контакты (которых в источниках больше нет) удаляются.
Ручные контакты (source='manual') не трогаются.

Источники: ЕГР (egr_company_contacts_history), МАРТ (trade_registry_records.object_contacts),
ГИАС (gias_accredited_customers), ПВТ (pvt_resident_records.raw_json). Нормализация телефонов/
email — через общий app.services.contact_parser, чтобы логика не расходилась.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from sqlalchemy import delete, or_, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.logger import get_logger
from app.database.models import (
    CompanyContact,
    CompanyContactHistory,
    GiasAccreditedCustomer,
    PVTResidentRecord,
    TradeRegistryRecord,
)
from app.services.contact_parser import parse_contacts

logger = get_logger("company_contacts")

_BATCH = 2000
_LOCK_KEY = 911002   # фикс. ключ pg_advisory_lock — гарантия единственного прогона


def _norm(contact_type: str, value: str) -> str:
    """Ключ дедупа/поиска: телефон → только цифры, остальное → lower+trim."""
    if contact_type == "phone":
        return re.sub(r"\D", "", value)
    return value.strip().lower()


def _from_blob(company_id, unp, raw_text, source):
    """Телефоны/почты/прочее из свободного текста (через общий парсер)."""
    rows = []
    parsed = parse_contacts(raw_text)
    for v in parsed["phones"]:
        rows.append((company_id, unp, "phone", v, _norm("phone", v), source, raw_text))
    for v in parsed["emails"]:
        rows.append((company_id, unp, "email", v, _norm("email", v), source, raw_text))
    for v in parsed["other"]:
        rows.append((company_id, unp, "other", v, _norm("other", v), source, raw_text))
    return rows


def _website(company_id, unp, website, source):
    w = (website or "").strip()
    if not w:
        return []
    return [(company_id, unp, "website", w, _norm("website", w), source, website)]


def _unp_to_int(unp) -> int | None:
    if unp is None:
        return None
    digits = re.sub(r"\D", "", str(unp))
    return int(digits) if digits else None


def is_current_contact_period(valid_from, valid_to, on_date: date | None = None) -> bool:
    """Return whether a dated EGR contact is effective on the requested date."""
    current = on_date or date.today()
    return (valid_from is None or valid_from <= current) and (
        valid_to is None or valid_to >= current
    )


def _iter_source_contacts(read_db: Session):
    """Генерит кортежи (company_id, unp, type, value, value_norm, source, raw) из всех источников."""
    # ЕГР: phone/email/fax — свободный текст в колонках; website — отдельно
    q = read_db.query(
        CompanyContactHistory.company_id, CompanyContactHistory.phone,
        CompanyContactHistory.email, CompanyContactHistory.fax, CompanyContactHistory.website,
    ).filter(
        or_(
            CompanyContactHistory.valid_from.is_(None),
            CompanyContactHistory.valid_from <= date.today(),
        ),
        or_(
            CompanyContactHistory.valid_to.is_(None),
            CompanyContactHistory.valid_to >= date.today(),
        ),
    ).yield_per(_BATCH)
    for company_id, phone, email, fax, website in q:
        blob = " ".join(x for x in (phone, email, fax) if x)
        yield from _from_blob(company_id, None, blob, "egr")
        yield from _website(company_id, None, website, "egr")

    # МАРТ: object_contacts — свободный текст (телефоны/почты/домены вперемешку)
    q = read_db.query(
        TradeRegistryRecord.company_id, TradeRegistryRecord.unp, TradeRegistryRecord.object_contacts,
    ).filter(TradeRegistryRecord.object_contacts.isnot(None)).yield_per(_BATCH)
    for company_id, unp, contacts in q:
        yield from _from_blob(company_id, unp, contacts, "mart")

    # ГИАС: phone/email + web_site (только привязанные к компании)
    q = read_db.query(
        GiasAccreditedCustomer.company_id, GiasAccreditedCustomer.unp,
        GiasAccreditedCustomer.phone, GiasAccreditedCustomer.email, GiasAccreditedCustomer.web_site,
    ).filter(GiasAccreditedCustomer.company_id.isnot(None)).yield_per(_BATCH)
    for company_id, unp, phone, email, web_site in q:
        unp_int = _unp_to_int(unp)
        blob = " ".join(x for x in (phone, email) if x)
        yield from _from_blob(company_id, unp_int, blob, "gias")
        yield from _website(company_id, unp_int, web_site, "gias")

    # ПВТ: контакты внутри raw_json (phone/website)
    q = read_db.query(
        PVTResidentRecord.company_id, PVTResidentRecord.unp, PVTResidentRecord.raw_json,
    ).yield_per(_BATCH)
    for company_id, unp, raw in q:
        raw = raw or {}
        yield from _from_blob(company_id, unp, raw.get("phone") or "", "pvt")
        yield from _website(company_id, unp, raw.get("website") or "", "pvt")


def rebuild_company_contacts(db: Session) -> dict:
    """Полная идемпотентная пересборка авто-контактов. db — сессия для записи.

    Защищена advisory-lock: два параллельных прогона невозможны (иначе дедлоки на
    конкурентных upsert). Если лок занят — выходим, не делая ничего.
    """
    got = db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _LOCK_KEY}).scalar()
    if not got:
        logger.warning("rebuild_company_contacts: уже выполняется в другом процессе — пропуск")
        return {"skipped": True}

    run_started = datetime.utcnow()
    batch: list[dict] = []
    batch_keys: set = set()   # антидубль ВНУТРИ одного INSERT (иначе ON CONFLICT упадёт)
    upserted = 0

    def flush():
        nonlocal upserted
        if not batch:
            return
        stmt = pg_insert(CompanyContact).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_company_contact",
            set_={
                "value": stmt.excluded.value,
                "unp": stmt.excluded.unp,
                "raw": stmt.excluded.raw,
                "last_seen_at": run_started,
            },
        )
        db.execute(stmt)
        db.commit()              # покоммитно — без гигантской транзакции
        upserted += len(batch)
        batch.clear()
        batch_keys.clear()

    # Отдельная read-сессия: yield_per держит серверный курсор, а писать будем через db.
    read_db = SessionLocal()
    try:
        for company_id, unp, ctype, value, vnorm, source, raw in _iter_source_contacts(read_db):
            if not value or not vnorm:
                continue
            key = (str(company_id), ctype, vnorm, source)
            if key in batch_keys:
                continue
            batch_keys.add(key)
            batch.append({
                "company_id": company_id, "unp": unp, "contact_type": ctype,
                "value": value, "value_norm": vnorm, "source": source, "raw": raw,
                "last_seen_at": run_started,
            })
            if len(batch) >= _BATCH:
                flush()
        flush()

        # Устаревшие авто-контакты (не встретились в прогоне) удаляем; ручные не трогаем.
        pruned = db.execute(
            delete(CompanyContact).where(
                CompanyContact.source != "manual",
                CompanyContact.last_seen_at < run_started,
            )
        ).rowcount
        db.commit()
    finally:
        read_db.close()
        db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_KEY})
        db.commit()

    logger.info("company_contacts rebuilt: upserted=%s pruned=%s", upserted, pruned)
    return {"upserted": upserted, "pruned": pruned}
