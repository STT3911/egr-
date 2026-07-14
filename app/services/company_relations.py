"""Поиск связанных компаний: по общим контактам (телефон/email) и по адресу (здание).

Читает уже собранные агрегаты `company_contacts` и `company_address_keys` —
без парсинга на лету, быстрые индексированные запросы (см. app.services.company_contacts,
app.services.company_addresses — там периодическая сборка этих таблиц).
"""
from __future__ import annotations

from sqlalchemy import bindparam, text
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


def _company_ids_by_unp(db: Session, unps: list[int]) -> dict[int, str]:
    if not unps:
        return {}
    statement = text(
        "SELECT unp, id FROM egr_companies WHERE unp IN :unps"
    ).bindparams(bindparam("unps", expanding=True))
    rows = db.execute(statement, {"unps": unps}).mappings().all()
    return {int(row["unp"]): str(row["id"]) for row in rows}


def _company_names_by_unp(db: Session, unps: list[int]) -> dict[int, str | None]:
    if not unps:
        return {}
    statement = text(
        """
        SELECT c.unp, COALESCE(n.full_name_ru, n.short_name_ru, n.full_name_by) AS name
        FROM egr_companies c
        LEFT JOIN LATERAL (
            SELECT full_name_ru, short_name_ru, full_name_by
            FROM egr_company_names_history
            WHERE company_id = c.id
            ORDER BY (valid_to IS NULL) DESC, valid_to DESC NULLS LAST, valid_from DESC NULLS LAST
            LIMIT 1
        ) n ON true
        WHERE c.unp IN :unps
        """
    ).bindparams(bindparam("unps", expanding=True))
    rows = db.execute(statement, {"unps": unps}).mappings().all()
    return {int(row["unp"]): row["name"] for row in rows}


def build_relation_graph(
    db: Session,
    company_id,
    root_unp: int,
    *,
    depth: int = 2,
    max_nodes: int = 40,
) -> dict:
    """Build a bounded company relation graph from shared contacts and addresses."""
    nodes: dict[int, dict] = {
        root_unp: {"unp": root_unp, "name": None, "depth": 0, "relation_count": 0}
    }
    edges: dict[tuple, dict] = {}
    frontier: list[tuple[str, int]] = [(str(company_id), root_unp)]
    per_node_limit = max(6, min(16, max_nodes // 2))
    was_truncated = False

    def add_edge(source_unp: int, target_unp: int, relation_type: str, value: str | None) -> None:
        if source_unp == target_unp:
            return
        pair = tuple(sorted((source_unp, target_unp)))
        key = (*pair, relation_type, value or "")
        if key not in edges:
            edges[key] = {
                "source_unp": source_unp,
                "target_unp": target_unp,
                "type": relation_type,
                "value": value,
            }

    for current_depth in range(1, depth + 1):
        discovered_unps: list[int] = []
        for source_id, source_unp in frontier:
            related_rows = [
                *find_related_by_contact(db, source_id, limit=per_node_limit),
                *find_related_by_address(db, source_id, limit=per_node_limit),
            ]
            for related in related_rows:
                target_unp = int(related["unp"])
                if "matched_type" in related:
                    relation_type = related["matched_type"]
                    value = related.get("matched_value")
                else:
                    relation_type = "address"
                    value = related.get("address")

                if target_unp in nodes:
                    add_edge(source_unp, target_unp, relation_type, value)
                    continue
                if len(nodes) >= max_nodes:
                    was_truncated = True
                    continue

                nodes[target_unp] = {
                    "unp": target_unp,
                    "name": related.get("name"),
                    "depth": current_depth,
                    "relation_count": 0,
                }
                discovered_unps.append(target_unp)
                add_edge(source_unp, target_unp, relation_type, value)

        if current_depth >= depth or not discovered_unps:
            break
        expandable_unps = list(dict.fromkeys(discovered_unps))[:12]
        id_map = _company_ids_by_unp(db, expandable_unps)
        frontier = [(company_id, unp) for unp, company_id in id_map.items()]

    names = _company_names_by_unp(db, list(nodes))
    for unp, node in nodes.items():
        node["name"] = names.get(unp) or node["name"]

    for edge in edges.values():
        nodes[edge["source_unp"]]["relation_count"] += 1
        nodes[edge["target_unp"]]["relation_count"] += 1

    edge_items = list(edges.values())
    return {
        "root_unp": root_unp,
        "depth": depth,
        "nodes": sorted(nodes.values(), key=lambda node: (node["depth"], -node["relation_count"], node["unp"])),
        "edges": edge_items,
        "stats": {
            "companies": len(nodes),
            "connections": len(edge_items),
            "phones": sum(edge["type"] == "phone" for edge in edge_items),
            "emails": sum(edge["type"] == "email" for edge in edge_items),
            "addresses": sum(edge["type"] == "address" for edge in edge_items),
        },
        "truncated": was_truncated,
    }
