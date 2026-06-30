"""Import helpers for EAEU SEZ resident registry snapshots."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert


TEXT_FIELDS = [
    "country",
    "full_name",
    "short_name",
    "legal_address",
    "firm_name",
    "registration_agency",
    "sez_name",
    "project_name",
    "registry_entry_date",
    "certificate",
    "source_url",
]


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return None if text in {"", "\ufffd"} else text


def clean_belarus_unp(value: Any) -> int | None:
    digits = re.sub(r"\D+", "", str(value or ""))
    return int(digits) if len(digits) == 9 else None


def load_snapshot(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON list in {path}")
    rows: list[dict[str, Any]] = []
    seen_item_ids: set[int] = set()
    for row in data:
        if not isinstance(row, dict):
            continue
        try:
            item_id = int(row["item_id"])
        except (KeyError, TypeError, ValueError):
            rows.append(row)
            continue
        if item_id in seen_item_ids:
            continue
        seen_item_ids.add(item_id)
        rows.append(row)
    return rows


def company_map_for_unps(db: Any, unps: set[int]) -> dict[int, Any]:
    from app.database.models import Company

    if not unps:
        return {}
    rows = db.query(Company.unp, Company.id).filter(Company.unp.in_(sorted(unps))).all()
    return {int(unp): company_id for unp, company_id in rows}


def normalize_row(row: dict[str, Any], company_id: Any, unp: int) -> dict[str, Any]:
    item_id = row.get("item_id")
    if item_id is None:
        raise ValueError("Missing item_id")

    now = datetime.utcnow()
    payload = {
        "item_id": int(item_id),
        "company_id": company_id,
        "unp": unp,
        "raw_json": {**row, "firm_name": clean_text(row.get("firm_name"))},
        "last_seen_at": now,
        "updated_at": now,
    }
    for field in TEXT_FIELDS:
        payload[field] = clean_text(row.get(field))
    return payload


def upsert_rows(db: Any, payloads: list[dict[str, Any]]) -> None:
    from app.database.models import EAEUSEZResidentRecord

    if not payloads:
        return
    stmt = pg_insert(EAEUSEZResidentRecord).values(payloads)
    stmt = stmt.on_conflict_do_update(
        index_elements=[EAEUSEZResidentRecord.item_id],
        set_={
            "company_id": stmt.excluded.company_id,
            "unp": stmt.excluded.unp,
            "country": stmt.excluded.country,
            "full_name": stmt.excluded.full_name,
            "short_name": stmt.excluded.short_name,
            "legal_address": stmt.excluded.legal_address,
            "firm_name": stmt.excluded.firm_name,
            "registration_agency": stmt.excluded.registration_agency,
            "sez_name": stmt.excluded.sez_name,
            "project_name": stmt.excluded.project_name,
            "registry_entry_date": stmt.excluded.registry_entry_date,
            "certificate": stmt.excluded.certificate,
            "source_url": stmt.excluded.source_url,
            "raw_json": stmt.excluded.raw_json,
            "last_seen_at": stmt.excluded.last_seen_at,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    db.execute(stmt)


def import_sez_snapshot_rows(db: Any, rows: list[dict[str, Any]], batch_size: int = 500) -> dict[str, int]:
    stats = {
        "total": 0,
        "invalid_item_id": 0,
        "invalid_unp": 0,
        "found_company": 0,
        "missing_company": 0,
        "saved": 0,
    }
    pending: list[dict[str, Any]] = []

    unps = {unp for row in rows if (unp := clean_belarus_unp(row.get("tax_id")))}
    company_ids = company_map_for_unps(db, unps)

    for row in rows:
        stats["total"] += 1
        if row.get("item_id") is None:
            stats["invalid_item_id"] += 1
            continue
        unp = clean_belarus_unp(row.get("tax_id"))
        if unp is None:
            stats["invalid_unp"] += 1
            continue
        company_id = company_ids.get(unp)
        if company_id is None:
            stats["missing_company"] += 1
            continue

        pending.append(normalize_row(row, company_id, unp))
        stats["found_company"] += 1
        stats["saved"] += 1

        if len(pending) >= batch_size:
            upsert_rows(db, pending)
            db.commit()
            pending.clear()

    if pending:
        upsert_rows(db, pending)
        db.commit()

    return stats


def import_sez_snapshot_json(db: Any, snapshot_path: Path, batch_size: int = 500) -> dict[str, int]:
    return import_sez_snapshot_rows(db, load_snapshot(snapshot_path), batch_size=batch_size)


def sync_eaeu_sez_residents(
    db: Any,
    country: str = "Беларусь",
    timeout: float = 30.0,
    delay: float = 0.2,
    retries: int = 2,
    limit_pages: int | None = None,
    batch_size: int = 500,
) -> dict[str, Any]:
    """Полный авто-синк СЭЗ: выгрузить реестр (с пагинацией) и обновить БД апсёртом.

    Без промежуточных файлов и без удаления: записи обновляются по item_id,
    исчезнувшие из реестра остаются, last_seen_at пишется на каждый апсёрт.
    """
    from app.services.eaeu_sez_fetch import fetch_rows

    rows, fetch_stats = fetch_rows(
        country=country,
        timeout=timeout,
        delay=delay,
        limit_pages=limit_pages,
        retries=retries,
        quiet=True,
        on_date=None,
    )
    import_stats = import_sez_snapshot_rows(db, rows, batch_size=batch_size)
    return {"fetch": fetch_stats, "import": import_stats}
