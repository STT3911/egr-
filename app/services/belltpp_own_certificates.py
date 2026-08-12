"""Fetch and import BelTPP own-production certificates."""

from __future__ import annotations

import hashlib
import html
import json
import math
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin

import requests


BASE_URL = "https://www.cci.by/certs/own/"
DEFAULT_PAGE_SIZE = 20
USER_AGENT = "Mozilla/5.0 (compatible; EGR-Service/1.0; +https://company.tenders.by)"


@dataclass(frozen=True)
class ParsedBeltppOwnCertificate:
    values: dict[str, Any]


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def parse_date(value: str | None) -> date | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        return None


def stable_hash(payload: dict[str, Any]) -> str:
    dumped = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


def fetch_page(
    page: int,
    page_size: int = DEFAULT_PAGE_SIZE,
    *,
    timeout: float = 30.0,
    retries: int = 3,
    retry_delay: float = 2.0,
) -> tuple[str, str]:
    url = f"{BASE_URL}?np={page}&ps={page_size}"
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
                timeout=timeout,
            )
            response.raise_for_status()
            return response.text, response.url
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(retry_delay * attempt)
    raise RuntimeError(f"Failed to fetch BelTPP page {page} after {retries} attempts: {last_error}") from last_error


def parse_total_count(html_text: str) -> int | None:
    match = re.search(r"Предприятий:\s*(\d+)", html_text)
    return int(match.group(1)) if match else None


def parse_product_rows(products_html: str) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    for row_match in re.finditer(
        r"<tr>\s*<td>(?P<num>.*?)</td>\s*<td>(?P<name>.*?)</td>\s*<td>(?P<code>.*?)</td>\s*</tr>",
        products_html,
        re.IGNORECASE | re.DOTALL,
    ):
        row_no_digits = re.sub(r"\D+", "", clean_text(row_match.group("num")) or "")
        products.append(
            {
                "row_no": int(row_no_digits) if row_no_digits else None,
                "name": clean_text(row_match.group("name")),
                "code": clean_text(row_match.group("code")),
            }
        )
    return products


def parse_cert_text(text: str) -> dict[str, Any] | None:
    cleaned = clean_text(text) or ""
    match = re.search(
        r"(?P<cert>\S+)\s+от\s+(?P<issue>\d{2}\.\d{2}\.\d{4})\s+на\s+бланке\s+№\s*(?P<blank>\S+)\.\s*Действителен\s+до\s+(?P<valid>\d{2}\.\d{2}\.\d{4})",
        cleaned,
        re.IGNORECASE,
    )
    if not match:
        return None
    return {
        "cert_number": match.group("cert"),
        "blank_number": match.group("blank"),
        "issue_date": parse_date(match.group("issue")),
        "valid_until": parse_date(match.group("valid")),
        "certificate_text": cleaned,
    }


def parse_page(html_text: str, source_url: str, source_page: int) -> list[ParsedBeltppOwnCertificate]:
    company_matches = list(
        re.finditer(
            r"<tr>\s*<td\s+valign='top'\s+class='etitle'>\s*<b>(?P<position>\d+)\.\s*</b>\s*</td>\s*"
            r"<td\s+valign='top'>\s*<b>(?P<holder>.*?)\s*\[УНП:\s*(?P<unp>\d{9})\]\s*</b>\s*</td>\s*</tr>",
            html_text,
            re.IGNORECASE | re.DOTALL,
        )
    )
    parsed: list[ParsedBeltppOwnCertificate] = []

    for index, company_match in enumerate(company_matches):
        section_start = company_match.end()
        section_end = company_matches[index + 1].start() if index + 1 < len(company_matches) else len(html_text)
        section = html_text[section_start:section_end]
        holder_name = clean_text(company_match.group("holder")) or ""
        holder_unp = int(company_match.group("unp"))
        source_position = int(company_match.group("position"))

        for cert_match in re.finditer(
            r"showCert\((?P<source_id>\d+)\).*?Сертификат:\s*(?P<cert_text>.*?)</a>\s*</b>\s*"
            r"<a\s+target=\"_check_own\"\s+href=\"(?P<verify_url>[^\"]+)\".*?"
            r"<div\s+class='products'\s+id='(?P=source_id)'[^>]*>\s*<table[^>]*>(?P<products>.*?)</table>\s*</div>",
            section,
            re.IGNORECASE | re.DOTALL,
        ):
            cert_parts = parse_cert_text(cert_match.group("cert_text"))
            if not cert_parts:
                continue
            products = parse_product_rows(cert_match.group("products"))
            verify_url = urljoin(source_url, html.unescape(cert_match.group("verify_url")))
            source_id = int(cert_match.group("source_id"))
            raw_json = {
                "holder_name": holder_name,
                "holder_unp": holder_unp,
                "source_id": source_id,
                "source_position": source_position,
                "certificate_text": cert_parts["certificate_text"],
                "products": products,
            }
            identity = {
                "cert_number": cert_parts["cert_number"],
                "blank_number": cert_parts["blank_number"],
                "issue_date": cert_parts["issue_date"],
            }
            values = {
                **identity,
                "company_id": None,
                "holder_unp": holder_unp,
                "holder_name": holder_name,
                "valid_until": cert_parts["valid_until"],
                "verify_url": verify_url,
                "source_url": source_url,
                "source_page": source_page,
                "source_position": source_position,
                "source_id": source_id,
                "products": products,
                "raw_json": raw_json,
            }
            values["sync_key"] = stable_hash(identity)
            values["sync_hash"] = stable_hash(values)
            parsed.append(ParsedBeltppOwnCertificate(values))
    return parsed


def fetch_all(
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int | None = None,
    delay: float = 0.2,
) -> tuple[list[ParsedBeltppOwnCertificate], dict[str, Any]]:
    first_html, first_url = fetch_page(1, page_size)
    total = parse_total_count(first_html)
    page_count = math.ceil(total / page_size) if total else 1
    if max_pages is not None:
        page_count = min(page_count, max_pages)

    rows = parse_page(first_html, first_url, 1)
    for page in range(2, page_count + 1):
        if delay > 0:
            time.sleep(delay)
        html_text, source_url = fetch_page(page, page_size)
        rows.extend(parse_page(html_text, source_url, page))

    return rows, {
        "source": BASE_URL,
        "fetched_at": datetime.utcnow().isoformat(),
        "total_companies": total or 0,
        "page_count": page_count,
        "page_size": page_size,
        "parsed": len(rows),
    }


def rows_to_snapshot(rows: list[ParsedBeltppOwnCertificate], stats: dict[str, Any]) -> dict[str, Any]:
    return {
        **stats,
        "items": [row.values for row in rows],
    }


def save_snapshot(path: Path, rows: list[ParsedBeltppOwnCertificate], stats: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = rows_to_snapshot(rows, stats)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {**stats, "output": str(path)}


def fetch_snapshot(
    output: Path,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int | None = None,
    delay: float = 0.2,
) -> dict[str, Any]:
    rows, stats = fetch_all(page_size=page_size, max_pages=max_pages, delay=delay)
    return save_snapshot(output, rows, stats)


def load_snapshot(path: Path) -> tuple[list[ParsedBeltppOwnCertificate], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError(f"Expected BelTPP snapshot object with items in {path}")
    rows = [
        ParsedBeltppOwnCertificate(item)
        for item in payload["items"]
        if isinstance(item, dict)
    ]
    stats = {
        "source": payload.get("source") or BASE_URL,
        "fetched_at": payload.get("fetched_at"),
        "total_companies": int(payload.get("total_companies") or 0),
        "page_count": int(payload.get("page_count") or 0),
        "page_size": int(payload.get("page_size") or 0),
        "parsed": len(rows),
        "input": str(path),
    }
    return rows, stats


def company_map_for_unps(db: Any, unps: set[int]) -> dict[int, Any]:
    from app.database.models import Company

    if not unps:
        return {}
    rows = db.query(Company.unp, Company.id).filter(Company.unp.in_(sorted(unps))).all()
    return {int(unp): company_id for unp, company_id in rows}


def import_certificate_rows(
    db: Any,
    rows: Iterable[ParsedBeltppOwnCertificate],
    *,
    batch_size: int = 500,
    dry_run: bool = False,
) -> dict[str, int]:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.database.models import BeltppOwnCertificate

    materialized = [row.values.copy() for row in rows]
    stats = {
        "parsed": len(materialized),
        "matched_companies": 0,
        "created_or_updated": 0,
        "dry_run": int(dry_run),
    }
    company_ids = company_map_for_unps(db, {int(row["holder_unp"]) for row in materialized})
    now = datetime.utcnow()
    for row in materialized:
        row["company_id"] = company_ids.get(int(row["holder_unp"]))
        if row["company_id"]:
            stats["matched_companies"] += 1
        row["last_seen_at"] = now
        row["updated_at"] = now

    if dry_run or not materialized:
        return stats

    for offset in range(0, len(materialized), batch_size):
        batch = materialized[offset : offset + batch_size]
        stmt = pg_insert(BeltppOwnCertificate).values(batch)
        excluded = stmt.excluded
        update_columns = {
            column.name: getattr(excluded, column.name)
            for column in BeltppOwnCertificate.__table__.columns
            if column.name not in {"id", "sync_key", "first_seen_at", "created_at"}
        }
        stmt = stmt.on_conflict_do_update(
            constraint="uq_belltpp_own_certificates_sync_key",
            set_=update_columns,
        )
        db.execute(stmt)
        stats["created_or_updated"] += len(batch)
    db.commit()
    return stats


def fetch_and_import(
    db: Any,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int | None = None,
    delay: float = 0.2,
    batch_size: int = 500,
    dry_run: bool = False,
    output: Path | None = None,
) -> dict[str, Any]:
    rows, fetch_stats = fetch_all(page_size=page_size, max_pages=max_pages, delay=delay)
    if output:
        fetch_stats = save_snapshot(output, rows, fetch_stats)
    import_stats = import_certificate_rows(db, rows, batch_size=batch_size, dry_run=dry_run)
    return {**fetch_stats, **import_stats}


def import_snapshot(
    db: Any,
    path: Path,
    *,
    batch_size: int = 500,
    dry_run: bool = False,
) -> dict[str, Any]:
    rows, snapshot_stats = load_snapshot(path)
    import_stats = import_certificate_rows(db, rows, batch_size=batch_size, dry_run=dry_run)
    return {**snapshot_stats, **import_stats}
