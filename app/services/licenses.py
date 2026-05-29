"""Fetch and import license.gov.by registry snapshots."""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("licenses")


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()
    return text or None


def parse_unp(value: Any) -> int | None:
    digits = re.sub(r"\D+", "", str(value or ""))
    return int(digits) if len(digits) == 9 else None


def parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.startswith("0001-01-01"):
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def stable_hash(payload: dict[str, Any]) -> str:
    dumped = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


def fetch_license_page(
    page: int,
    page_size: int,
    *,
    base_url: str | None = None,
    timeout: float | None = None,
    verify_tls: bool | None = None,
) -> dict[str, Any]:
    url = f"{(base_url or settings.LICENSE_API_URL).rstrip('/')}/getAllPaged"
    response = requests.get(
        url,
        params={"page": page, "pageSize": page_size},
        headers={"Accept": "application/json"},
        timeout=timeout or settings.LICENSE_TIMEOUT_SECONDS,
        verify=settings.LICENSE_VERIFY_TLS if verify_tls is None else verify_tls,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError(f"Unsupported license.gov.by response payload: {type(payload)!r}")
    return payload


def fetch_license_snapshot(
    output: Path,
    *,
    page_size: int | None = None,
    start_page: int = 1,
    max_pages: int | None = None,
    delay: float | None = None,
    verify_tls: bool | None = None,
) -> dict[str, Any]:
    resolved_page_size = page_size or settings.LICENSE_PAGE_SIZE
    resolved_delay = settings.LICENSE_PAGE_DELAY_SECONDS if delay is None else delay
    items: list[dict[str, Any]] = []
    page = start_page
    page_count: int | None = None
    total_count: int | None = None

    while True:
        payload = fetch_license_page(page, resolved_page_size, verify_tls=verify_tls)
        page_items = payload.get("items") or []
        items.extend(page_items)
        page_count = int(payload.get("pageCount") or page_count or page)
        total_count = int(payload.get("count") or total_count or 0)
        logger.info("Fetched license page %s/%s: %s rows", page, page_count, len(page_items))

        if not page_items:
            break
        if max_pages is not None and page - start_page + 1 >= max_pages:
            break
        if page >= page_count:
            break
        page += 1
        if resolved_delay > 0:
            time.sleep(resolved_delay)

    snapshot = {
        "source": "license.gov.by",
        "source_url": f"{settings.LICENSE_API_URL.rstrip('/')}/getAllPaged",
        "fetched_at": datetime.utcnow().isoformat(),
        "page_size": resolved_page_size,
        "start_page": start_page,
        "last_page": page,
        "page_count": page_count,
        "count": total_count,
        "items": items,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {
        "items": len(items),
        "count": total_count or len(items),
        "page_count": page_count or 0,
        "last_page": page,
        "output": str(output),
    }


def load_snapshot(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return [row for row in data["items"] if isinstance(row, dict)]
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    raise ValueError(f"Expected JSON list or snapshot object with items in {path}")


def company_map_for_unps(db: Any, unps: set[int]) -> dict[int, Any]:
    from app.database.models import Company

    if not unps:
        return {}
    rows = db.query(Company.unp, Company.id).filter(Company.unp.in_(sorted(unps))).all()
    return {int(unp): company_id for unp, company_id in rows}


def normalize_license_row(row: dict[str, Any], company_id: Any | None) -> dict[str, Any] | None:
    license_id = row.get("id")
    try:
        normalized_id = int(license_id)
    except (TypeError, ValueError):
        return None

    holder = row.get("licenseHolder") if isinstance(row.get("licenseHolder"), dict) else {}
    activity = row.get("reActivityType") if isinstance(row.get("reActivityType"), dict) else {}
    holder_unp = parse_unp(holder.get("unp"))
    now = datetime.utcnow()

    return {
        "license_id": normalized_id,
        "company_id": company_id,
        "holder_unp": holder_unp,
        "holder_name": clean_text(holder.get("name")),
        "generated_number": clean_text(row.get("generatedNumber")),
        "activity_type_id": int(activity["id"]) if str(activity.get("id", "")).isdigit() else None,
        "activity_type_code": clean_text(activity.get("code")),
        "activity_type_name": clean_text(activity.get("name")),
        "activity_date_start": parse_datetime(activity.get("dateStart")),
        "activity_date_end": parse_datetime(activity.get("dateEnd")),
        "activity_is_active": activity.get("isActive") if isinstance(activity.get("isActive"), bool) else None,
        "raw_json": row,
        "sync_hash": stable_hash(row),
        "last_seen_at": now,
        "updated_at": now,
    }


def existing_hashes(db: Any, license_ids: set[int]) -> dict[int, str]:
    from app.database.models import LicenseRecord

    if not license_ids:
        return {}
    rows = (
        db.query(LicenseRecord.license_id, LicenseRecord.sync_hash)
        .filter(LicenseRecord.license_id.in_(sorted(license_ids)))
        .all()
    )
    return {int(license_id): sync_hash for license_id, sync_hash in rows}


def upsert_license_rows(db: Any, payloads: list[dict[str, Any]]) -> None:
    from app.database.models import LicenseRecord

    if not payloads:
        return
    deduped = list({int(payload["license_id"]): payload for payload in payloads}.values())
    stmt = pg_insert(LicenseRecord).values(deduped)
    stmt = stmt.on_conflict_do_update(
        index_elements=[LicenseRecord.license_id],
        set_={
            "company_id": stmt.excluded.company_id,
            "holder_unp": stmt.excluded.holder_unp,
            "holder_name": stmt.excluded.holder_name,
            "generated_number": stmt.excluded.generated_number,
            "activity_type_id": stmt.excluded.activity_type_id,
            "activity_type_code": stmt.excluded.activity_type_code,
            "activity_type_name": stmt.excluded.activity_type_name,
            "activity_date_start": stmt.excluded.activity_date_start,
            "activity_date_end": stmt.excluded.activity_date_end,
            "activity_is_active": stmt.excluded.activity_is_active,
            "raw_json": stmt.excluded.raw_json,
            "sync_hash": stmt.excluded.sync_hash,
            "last_seen_at": stmt.excluded.last_seen_at,
            "updated_at": func.now(),
        },
    )
    db.execute(stmt)


def import_license_rows(db: Any, rows: list[dict[str, Any]], batch_size: int | None = None) -> dict[str, int]:
    resolved_batch_size = batch_size or settings.LICENSE_SAVE_EVERY
    stats = {
        "total": 0,
        "invalid": 0,
        "duplicate_license_ids": 0,
        "with_unp": 0,
        "matched_company": 0,
        "missing_company": 0,
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "saved": 0,
    }
    pending: list[dict[str, Any]] = []
    seen_license_ids: set[int] = set()

    unps: set[int] = set()
    license_ids: set[int] = set()
    for row in rows:
        holder = row.get("licenseHolder") if isinstance(row.get("licenseHolder"), dict) else {}
        if unp := parse_unp(holder.get("unp")):
            unps.add(unp)
        try:
            license_ids.add(int(row.get("id")))
        except (TypeError, ValueError):
            continue
    company_ids = company_map_for_unps(db, unps)
    known_hashes = existing_hashes(db, license_ids)

    for row in rows:
        stats["total"] += 1
        holder = row.get("licenseHolder") if isinstance(row.get("licenseHolder"), dict) else {}
        holder_unp = parse_unp(holder.get("unp"))
        if holder_unp is not None:
            stats["with_unp"] += 1
        company_id = company_ids.get(holder_unp) if holder_unp is not None else None
        if holder_unp is not None and company_id is not None:
            stats["matched_company"] += 1
        elif holder_unp is not None:
            stats["missing_company"] += 1

        payload = normalize_license_row(row, company_id)
        if payload is None:
            stats["invalid"] += 1
            continue
        if payload["license_id"] in seen_license_ids:
            stats["duplicate_license_ids"] += 1
            continue
        seen_license_ids.add(payload["license_id"])

        current_hash = known_hashes.get(payload["license_id"])
        if current_hash is None:
            stats["created"] += 1
        elif current_hash == payload["sync_hash"]:
            stats["unchanged"] += 1
        else:
            stats["updated"] += 1

        pending.append(payload)
        stats["saved"] += 1
        if len(pending) >= resolved_batch_size:
            upsert_license_rows(db, pending)
            db.commit()
            pending.clear()

    if pending:
        upsert_license_rows(db, pending)
        db.commit()

    return stats


def import_license_snapshot_json(db: Any, snapshot_path: Path, batch_size: int | None = None) -> dict[str, int]:
    return import_license_rows(db, load_snapshot(snapshot_path), batch_size=batch_size)


def check_license_api_changes(
    db: Any,
    *,
    pages: int = 1,
    page_size: int | None = None,
    verify_tls: bool | None = None,
) -> dict[str, int]:
    rows: list[dict[str, Any]] = []
    resolved_page_size = page_size or settings.LICENSE_PAGE_SIZE
    for page in range(1, max(1, pages) + 1):
        payload = fetch_license_page(page, resolved_page_size, verify_tls=verify_tls)
        rows.extend(payload.get("items") or [])
    return import_license_rows(db, rows)
