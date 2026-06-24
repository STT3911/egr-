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

from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.logger import get_logger

logger = get_logger("company_registry")


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
