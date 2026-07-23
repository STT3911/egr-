"""Единый реестр УНП: занос ГРП-находок в центральную таблицу egr_companies.

Принцип архитектуры: ВСЕ УНП живут в egr_companies (центр), остальные данные
связываются по УНП/company_id. Госорганы/бюджетные, найденные перебором ГРП
(см. scripts/unp_enumerate.py → grp_raw_data → grp_process_raw → grp_taxpayer_data),
в ЕГР отсутствуют, поэтому их нужно отдельно добавить в центральный реестр с
пометкой source='grp'. Имя кладём в историю имён (как у ЕГР-компаний), чтобы поиск
и классификатор работали единообразно.

Идемпотентно: повторный запуск не создаёт дублей (вставка только отсутствующих).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.logger import get_logger
from app.database.models import (
    Company,
    CompanyNameHistory,
    CompanyPlaceLocation,
    GrpTaxpayerData,
)
from app.services.search_index import enqueue_company_for_indexing
from app.utils.search_normalizer import normalize_company_name

logger = get_logger("company_registry")


def sync_company_from_grp(db: Session, unp: int) -> bool:
    """Create or enrich one central company record from parsed GRP data."""
    grp = db.query(GrpTaxpayerData).filter(GrpTaxpayerData.unp == unp).first()
    if not grp:
        return False

    company = db.query(Company).filter(Company.unp == unp).first()
    if company is None:
        company = Company(
            unp=unp,
            source="grp",
            registration_date=grp.registration_date,
        )
        db.add(company)
        db.flush()
    elif company.source == "grp" and not company.registration_date and grp.registration_date:
        company.registration_date = grp.registration_date

    current_name = (
        db.query(CompanyNameHistory)
        .filter(
            CompanyNameHistory.company_id == company.id,
            CompanyNameHistory.valid_to.is_(None),
        )
        .first()
    )
    if current_name is None and (grp.full_name or grp.short_name):
        full_name = grp.full_name or grp.short_name
        db.add(
            CompanyNameHistory(
                company_id=company.id,
                full_name_ru=full_name,
                short_name_ru=grp.short_name,
                search_name=normalize_company_name(full_name),
                valid_from=grp.registration_date,
                valid_to=None,
            )
        )

    if grp.address:
        place = (
            db.query(CompanyPlaceLocation)
            .filter(CompanyPlaceLocation.unp == unp)
            .first()
        )
        if place is None:
            place = CompanyPlaceLocation(
                unp=unp,
                raw_json={"source": "grp"},
                address=grp.address,
                fetched_at=datetime.now(),
            )
            db.add(place)
        elif not place.address:
            place.address = grp.address
            place.fetched_at = datetime.now()

    enqueue_company_for_indexing(db, unp)
    db.flush()
    return True


def sync_companies_from_grp() -> dict:
    """Добавляет в egr_companies те УНП из grp_taxpayer_data, которых там ещё нет.

    Создаёт:
      - строку egr_companies (source='grp', дата регистрации из ГРП);
      - текущую запись имени в egr_company_names_history (full/short из ГРП).
    Возвращает счётчики добавленного.
    """
    db = SessionLocal()
    stats = {"companies_added": 0, "names_added": 0}
    try:
        # 1) Компании: УНП из ГРП, которых нет в центральном реестре.
        res = db.execute(text("""
            INSERT INTO egr_companies (id, unp, source, registration_date, created_at, updated_at)
            SELECT gen_random_uuid(), g.unp, 'grp', g.registration_date, now(), now()
            FROM grp_taxpayer_data g
            LEFT JOIN egr_companies c ON c.unp = g.unp
            WHERE c.unp IS NULL
            ON CONFLICT (unp) DO NOTHING
        """))
        stats["companies_added"] = res.rowcount or 0
        db.commit()
        logger.info("egr_companies: добавлено из ГРП %d", stats["companies_added"])

        # 2) Имена: текущее наименование для ГРП-компаний, у которых истории имён нет.
        res = db.execute(text("""
            INSERT INTO egr_company_names_history
                (id, company_id, full_name_ru, short_name_ru, search_name, valid_from, valid_to)
            SELECT gen_random_uuid(), c.id, g.full_name, g.short_name,
                   lower(coalesce(g.full_name, '')), g.registration_date, NULL
            FROM egr_companies c
            JOIN grp_taxpayer_data g ON g.unp = c.unp
            LEFT JOIN egr_company_names_history n ON n.company_id = c.id
            WHERE c.source = 'grp' AND n.company_id IS NULL
        """))
        stats["names_added"] = res.rowcount or 0
        db.commit()
        logger.info("egr_company_names_history: добавлено %d", stats["names_added"])
    except Exception as e:
        db.rollback()
        logger.error("sync_companies_from_grp failed: %s", e)
        raise
    finally:
        db.close()
    return stats
