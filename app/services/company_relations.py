"""Поиск связанных компаний: по общим контактам (телефон/email) и по адресу (здание).

Читает уже собранные агрегаты `company_contacts` и `company_address_keys` —
без парсинга на лету, быстрые индексированные запросы (см. app.services.company_contacts,
app.services.company_addresses — там периодическая сборка этих таблиц).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

# Пороги настраиваются через .env (RELATED_MIN_PHONE_DIGITS, RELATED_MAX_CLUSTER_SIZE) —
# подбираются на реальных данных без пересборки кода (правка .env + рестарт контейнера).
#
# RELATED_MIN_PHONE_DIGITS: телефоны короче этого — часто локальные номера без кода
# города (встречается в ЕГР); совпадение таких коротких номеров у разных компаний с
# высокой вероятностью случайное, а не признак реальной связи. Email такому риску не
# подвержен — не фильтруем.
#
# RELATED_MAX_CLUSTER_SIZE: кластеры больше этого — почти наверняка технический
# контакт/адрес (общий call-центр, хостинг-почта, массовый юридический адрес
# бизнес-центра), а не признак реальной связи. Отсекаем и в bulk-списках, и в выдаче
# по одной компании — иначе карточка одной компании тонет в сотнях нерелевантных
# "совпадений".

_RELATED_BY_CONTACT_SQL = text(
    """
    WITH mine AS (
        SELECT DISTINCT contact_type, value_norm
        FROM company_contacts
        WHERE company_id = :company_id
          AND contact_type IN ('phone', 'email')
          AND (contact_type != 'phone' OR length(value_norm) >= :min_phone_digits)
    ),
    mine_sized AS (
        SELECT m.contact_type, m.value_norm
        FROM mine m
        JOIN company_contacts cc2 ON cc2.contact_type = m.contact_type AND cc2.value_norm = m.value_norm
        GROUP BY m.contact_type, m.value_norm
        HAVING count(DISTINCT cc2.company_id) BETWEEN 2 AND :max_cluster_size
    )
    SELECT cc.contact_type, cc.value_norm, cc.value, c.unp,
           COALESCE(n.full_name_ru, n.short_name_ru) AS name
    FROM company_contacts cc
    JOIN mine_sized m ON m.contact_type = cc.contact_type AND m.value_norm = cc.value_norm
    JOIN egr_companies c ON c.id = cc.company_id
    LEFT JOIN LATERAL (
        SELECT full_name_ru, short_name_ru
        FROM egr_company_names_history
        WHERE company_id = cc.company_id
        ORDER BY (valid_to IS NULL) DESC, valid_to DESC NULLS LAST, valid_from DESC NULLS LAST
        LIMIT 1
    ) n ON true
    WHERE cc.company_id != :company_id
    ORDER BY cc.contact_type, cc.value_norm, c.unp
    LIMIT :limit
    """
)

_RELATED_BY_ADDRESS_SQL = text(
    """
    WITH mine AS (
        SELECT address_key FROM company_address_keys
        WHERE company_id = :company_id AND address_key IS NOT NULL
    ),
    mine_sized AS (
        SELECT m.address_key
        FROM mine m
        JOIN company_address_keys k2 ON k2.address_key = m.address_key
        GROUP BY m.address_key
        HAVING count(DISTINCT k2.company_id) BETWEEN 2 AND :max_cluster_size
    )
    SELECT k.unp, k.full_address,
           COALESCE(n.full_name_ru, n.short_name_ru) AS name
    FROM company_address_keys k
    JOIN mine_sized m ON m.address_key = k.address_key
    LEFT JOIN LATERAL (
        SELECT full_name_ru, short_name_ru
        FROM egr_company_names_history
        WHERE company_id = k.company_id
        ORDER BY (valid_to IS NULL) DESC, valid_to DESC NULLS LAST, valid_from DESC NULLS LAST
        LIMIT 1
    ) n ON true
    WHERE k.company_id != :company_id
    ORDER BY k.unp
    LIMIT :limit
    """
)


def find_related_by_contact(db: Session, company_id, limit: int = 100) -> list[dict]:
    """Другие компании, у которых совпадает хотя бы один телефон/email с данной.

    Кластеры крупнее RELATED_MAX_CLUSTER_SIZE (вероятно, технический общий контакт) исключены.
    """
    rows = db.execute(
        _RELATED_BY_CONTACT_SQL,
        {
            "company_id": str(company_id),
            "min_phone_digits": settings.RELATED_MIN_PHONE_DIGITS,
            "max_cluster_size": settings.RELATED_MAX_CLUSTER_SIZE,
            "limit": limit,
        },
    ).mappings().all()
    return [
        {
            "unp": int(r["unp"]),
            "name": r["name"],
            "matched_type": r["contact_type"],
            "matched_value": r["value"],
        }
        for r in rows
    ]


def find_related_by_address(db: Session, company_id, limit: int = 100) -> list[dict]:
    """Другие компании с тем же текущим адресом (здание, без учёта квартиры/офиса).

    Кластеры крупнее RELATED_MAX_CLUSTER_SIZE (вероятно, массовый юридический адрес
    бизнес-центра) исключены.
    """
    rows = db.execute(
        _RELATED_BY_ADDRESS_SQL,
        {"company_id": str(company_id), "max_cluster_size": settings.RELATED_MAX_CLUSTER_SIZE, "limit": limit},
    ).mappings().all()
    return [
        {"unp": int(r["unp"]), "name": r["name"], "address": r["full_address"]}
        for r in rows
    ]
