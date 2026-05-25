"""Client, parser, and DB sync for park.by HTP/PVT residents."""

from __future__ import annotations

import csv
import html
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode, urljoin

import requests

from app.core.logger import get_logger

logger = get_logger("park_residents")

BASE_URL = "https://www.park.by/residents/"

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) "
        "Gecko/20100101 Firefox/150.0"
    ),
}


@dataclass
class ParkResidentResult:
    unp: str
    status: str
    name: str | None = None
    profile_url: str | None = None
    description: str | None = None
    count: int | None = None
    source_url: str | None = None
    raw_text: str | None = None
    http_status: int | None = None
    error: str | None = None


class _NewsItemParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, Any]] = []
        self._item: dict[str, Any] | None = None
        self._div_depth = 0
        self._skip_depth = 0
        self._link_href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return

        class_names = set((attrs_dict.get("class") or "").split())
        if tag == "div" and "news-item" in class_names:
            self._item = {"texts": [], "links": []}
            self._div_depth = 1
            return

        if self._item is None:
            return

        if tag == "div":
            self._div_depth += 1
        elif tag == "a" and attrs_dict.get("href"):
            self._link_href = attrs_dict["href"]
            self._link_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return

        if self._item is None:
            return

        if tag == "a" and self._link_href:
            text = clean_text(" ".join(self._link_text))
            if text:
                self._item["links"].append({"text": text, "href": self._link_href})
            self._link_href = None
            self._link_text = []
        elif tag == "div":
            self._div_depth -= 1
            if self._div_depth <= 0:
                self.items.append(self._item)
                self._item = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._item is None:
            return
        text = clean_text(data)
        if not text:
            return
        self._item["texts"].append(text)
        if self._link_href:
            self._link_text.append(text)


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = html.unescape(str(value)).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def clean_unp(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    return digits if len(digits) >= 9 else None


def request_params(unp: str) -> dict[str, str]:
    return {
        "q": "",
        "UNP": unp,
        "save": "Найти",
        "search": "Y",
        "STAFF": "",
        "EXPER": "",
    }


def source_url(unp: str) -> str:
    return f"{BASE_URL}?{urlencode(request_params(unp))}"


def parse_count(html_text: str) -> int | None:
    match = re.search(r"Всего:\s*<[^>]+>\s*(\d+)\s+компан", html_text, re.IGNORECASE)
    if not match:
        match = re.search(r"Всего:\s*(\d+)\s+компан", html_text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def parse_resident_html(unp: str, html_text: str, http_status: int | None = None, url: str | None = None) -> ParkResidentResult:
    parser = _NewsItemParser()
    parser.feed(html_text)
    count = parse_count(html_text)
    if not parser.items:
        return ParkResidentResult(
            unp=unp,
            status="not_found",
            count=count,
            source_url=url,
            http_status=http_status,
        )

    item = parser.items[0]
    links = item.get("links") or []
    texts = [text for text in item.get("texts", []) if text]
    first_link = links[0] if links else {}
    name = clean_text(first_link.get("text")) or (texts[0] if texts else None)
    profile_url = urljoin(BASE_URL, first_link.get("href")) if first_link.get("href") else None
    description_parts = [text for text in texts if text != name]
    description = clean_text(" ".join(description_parts))

    return ParkResidentResult(
        unp=unp,
        status="found",
        name=name,
        profile_url=profile_url,
        description=description,
        count=count,
        source_url=url,
        raw_text="\n".join(texts) if texts else None,
        http_status=http_status,
    )


def fetch_resident(
    unp: str | int,
    session: requests.Session | None = None,
    timeout: float = 30.0,
    proxy: str | None = None,
) -> ParkResidentResult:
    parsed_unp = clean_unp(unp)
    if not parsed_unp:
        return ParkResidentResult(unp=str(unp), status="invalid", error="Invalid UNP")

    client = session or requests.Session()
    proxies = {"http": proxy, "https": proxy} if proxy else None
    url = source_url(parsed_unp)
    response = client.get(
        BASE_URL,
        params=request_params(parsed_unp),
        headers=DEFAULT_HEADERS,
        timeout=timeout,
        proxies=proxies,
    )
    return parse_resident_html(parsed_unp, response.text, response.status_code, url)


def upsert_resident_record(db: Any, company_id: Any, result: ParkResidentResult) -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.database.models import PVTResidentRecord

    now = datetime.utcnow()
    values = {
        "company_id": company_id,
        "unp": int(result.unp),
        "name": result.name,
        "profile_url": result.profile_url,
        "description": result.description,
        "source_url": result.source_url,
        "raw_json": asdict(result),
        "last_seen_at": now,
        "updated_at": now,
    }
    stmt = pg_insert(PVTResidentRecord).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[PVTResidentRecord.unp],
        set_={
            "company_id": stmt.excluded.company_id,
            "name": stmt.excluded.name,
            "profile_url": stmt.excluded.profile_url,
            "description": stmt.excluded.description,
            "source_url": stmt.excluded.source_url,
            "raw_json": stmt.excluded.raw_json,
            "last_seen_at": stmt.excluded.last_seen_at,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    db.execute(stmt)


def iter_unps_from_csv(path: Path, limit: int | None = None) -> list[str]:
    unps: list[str] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(handle, dialect=dialect)
        for row in reader:
            value = (
                row.get("unp")
                or row.get("UNP")
                or row.get("УНП")
                or row.get("__parsed_unp")
                or next((item for item in row.values() if clean_unp(item)), None)
            )
            unp = clean_unp(value)
            if not unp or unp in seen:
                continue
            seen.add(unp)
            unps.append(unp)
            if limit and len(unps) >= limit:
                break
    return unps


def write_results(path: Path, rows: list[ParkResidentResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps([asdict(row) for row in rows], ensure_ascii=False, indent=2), encoding="utf-8")
        return

    fieldnames = list(asdict(ParkResidentResult(unp="", status="")).keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def sync_pvt_residents(
    db: Any,
    limit: int | None = None,
    offset: int = 0,
    start_unp: int | None = None,
    batch_size: int = 100,
    delay: float = 0.2,
    timeout: float = 30.0,
    only_missing: bool = False,
    proxy: str | None = None,
) -> dict[str, int]:
    from app.database.models import Company, PVTResidentRecord

    stats = {"checked": 0, "found": 0, "not_found": 0, "invalid": 0, "error": 0, "saved": 0}
    session = requests.Session()
    pending = 0
    remaining = limit
    last_unp: int | None = start_unp - 1 if start_unp is not None else None
    offset_applied = False

    while remaining is None or remaining > 0:
        page_size = batch_size if remaining is None else min(batch_size, remaining)
        query = db.query(Company.id, Company.unp)
        if only_missing:
            query = query.outerjoin(PVTResidentRecord, PVTResidentRecord.company_id == Company.id).filter(PVTResidentRecord.id.is_(None))
        if last_unp is not None:
            query = query.filter(Company.unp > last_unp)
        query = query.order_by(Company.unp)
        if offset and not offset_applied:
            query = query.offset(offset)
            offset_applied = True

        rows = query.limit(page_size).all()
        if not rows:
            break

        for company_id, unp in rows:
            last_unp = int(unp)
            try:
                result = fetch_resident(str(unp), session=session, timeout=timeout, proxy=proxy)
                stats["checked"] += 1
                stats[result.status] = stats.get(result.status, 0) + 1
                if result.status == "found":
                    upsert_resident_record(db, company_id, result)
                    stats["saved"] += 1
                    pending += 1
                if pending >= batch_size:
                    db.commit()
                    pending = 0
                logger.info("PVT resident check unp=%s status=%s", unp, result.status)
            except Exception as exc:
                db.rollback()
                pending = 0
                stats["checked"] += 1
                stats["error"] += 1
                logger.warning("PVT resident check failed unp=%s error=%s", unp, exc)
            if delay > 0:
                time.sleep(delay)

        if remaining is not None:
            remaining -= len(rows)
        if len(rows) < page_size:
            break

    if pending:
        db.commit()
    return stats
