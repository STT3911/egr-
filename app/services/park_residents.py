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
PVT_LAST_CHECKED_UNP_KEY = "pvt_residents_last_checked_unp"
DEFAULT_CATALOG_PREFIXES = "АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЭЮЯ123456789"

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
    city: str | None = None
    legal_address: str | None = None
    phone: str | None = None
    website: str | None = None
    activity_directions: list[str] | None = None
    list_letter: str | None = None
    list_page: int | None = None
    list_description: str | None = None


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


def get_last_checked_unp(db: Any) -> int | None:
    from app.database.models import SystemState

    state = db.query(SystemState).filter(SystemState.key == PVT_LAST_CHECKED_UNP_KEY).first()
    if not state or not state.value:
        return None
    try:
        return int(state.value)
    except (TypeError, ValueError):
        logger.warning("Invalid PVT cursor value: %s", state.value)
        return None


def set_last_checked_unp(db: Any, unp: int | None) -> None:
    from app.database.models import SystemState

    value = "" if unp is None else str(int(unp))
    state = db.query(SystemState).filter(SystemState.key == PVT_LAST_CHECKED_UNP_KEY).first()
    if state:
        state.value = value
    else:
        db.add(SystemState(key=PVT_LAST_CHECKED_UNP_KEY, value=value))


def commit_pvt_cursor(db: Any, unp: int | None) -> None:
    try:
        set_last_checked_unp(db, unp)
        db.commit()
    except Exception:
        db.rollback()
        set_last_checked_unp(db, unp)
        db.commit()


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


def _strip_tags(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"</p\s*>", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    return clean_text(value) or ""


def _extract_first(pattern: str, html_text: str, flags: int = re.IGNORECASE | re.DOTALL) -> str | None:
    match = re.search(pattern, html_text, flags)
    if not match:
        return None
    for group in match.groups():
        if group:
            return clean_text(_strip_tags(group))
    return None


def catalog_url(letter: str | None = None, page: int = 1) -> str:
    params: dict[str, Any] = {}
    if letter:
        params["first"] = letter
    if page > 1:
        params["PAGEN_1"] = page
    query = urlencode(params)
    return f"{BASE_URL}?{query}" if query else BASE_URL


def parse_catalog_items(html_text: str, letter: str | None = None, page: int | None = None) -> list[dict[str, Any]]:
    parser = _NewsItemParser()
    parser.feed(html_text)
    items: list[dict[str, Any]] = []
    for item in parser.items:
        links = item.get("links") or []
        first_link = links[0] if links else {}
        href = first_link.get("href")
        name = clean_text(first_link.get("text"))
        if not href or not name:
            continue
        texts = [text for text in item.get("texts", []) if text and text != name]
        items.append(
            {
                "name": name,
                "profile_url": urljoin(BASE_URL, href),
                "profile_path": href,
                "list_description": clean_text(" ".join(texts)),
                "list_letter": letter,
                "list_page": page,
            }
        )
    return items


def has_next_catalog_page(html_text: str) -> bool:
    return 'id="ajax_next_page"' in html_text or "id='ajax_next_page'" in html_text


def parse_resident_detail_html(
    html_text: str,
    url: str | None = None,
    list_item: dict[str, Any] | None = None,
    http_status: int | None = None,
) -> ParkResidentResult:
    list_item = list_item or {}
    name = _extract_first(r"<h1[^>]*>(.*?)</h1>", html_text) or clean_text(list_item.get("name"))
    unp = clean_unp(_extract_first(r"УНП\s*:\s*([^<]+)", html_text))
    city = _extract_first(r"Город:\s*(?:<[^>]+>)*\s*(.*?)(?:</div>|<div)", html_text)
    legal_address = _extract_first(r"Юридический адрес:\s*(.*?)(?:</div>|<div)", html_text)
    phone = _extract_first(r"Контактный телефон:\s*(.*?)(?:</div>|<div)", html_text)
    website = _extract_first(
        r"Веб-сайт:\s*(?:<a[^>]*href=[\"']([^\"']+)[\"'][^>]*>.*?</a>|(.*?))(?:</div>|<div)",
        html_text,
    )
    if not website:
        website = _extract_first(r"Веб-сайт:\s*(.*?)(?:</div>|<div)", html_text)

    direction_html = None
    direction_match = re.search(r"Направления деятельности:\s*<ul>(.*?)</ul>", html_text, re.IGNORECASE | re.DOTALL)
    if direction_match:
        direction_html = direction_match.group(1)
    directions = []
    if direction_html:
        directions = [
            value
            for value in (
                clean_text(_strip_tags(item))
                for item in re.findall(r"<li[^>]*>(.*?)</li>", direction_html, re.IGNORECASE | re.DOTALL)
            )
            if value
        ]

    description = _extract_first(r'<div class="left-colum white_bgr">\s*(.*?)(?:<div class="block-unde">)', html_text)
    if description and name:
        description = clean_text(description.replace(name, "", 1))

    return ParkResidentResult(
        unp=unp or "",
        status="found" if unp else "invalid",
        name=name,
        profile_url=url or clean_text(list_item.get("profile_url")),
        description=description or clean_text(list_item.get("list_description")),
        source_url=url,
        http_status=http_status,
        error=None if unp else "UNP not found on detail page",
        city=city,
        legal_address=legal_address,
        phone=phone,
        website=website,
        activity_directions=directions or None,
        list_letter=clean_text(list_item.get("list_letter")),
        list_page=list_item.get("list_page") if isinstance(list_item.get("list_page"), int) else None,
        list_description=clean_text(list_item.get("list_description")),
    )


def fetch_catalog_snapshot(
    output: Path | None = None,
    letters: Iterable[str] | None = None,
    delay: float = 0.2,
    timeout: float = 30.0,
    proxy: str | None = None,
    limit: int | None = None,
) -> list[ParkResidentResult]:
    letters = list(letters or DEFAULT_CATALOG_PREFIXES)
    session = requests.Session()
    proxies = {"http": proxy, "https": proxy} if proxy else None
    results: list[ParkResidentResult] = []
    seen_urls: set[str] = set()

    for letter in letters:
        page = 1
        while True:
            page_url = catalog_url(letter, page)
            response = session.get(page_url, headers=DEFAULT_HEADERS, timeout=timeout, proxies=proxies)
            response.raise_for_status()
            items = parse_catalog_items(response.text, letter=letter, page=page)
            logger.info("PVT catalog letter=%s page=%s items=%s", letter, page, len(items))
            if not items:
                break

            for item in items:
                profile_url = str(item["profile_url"])
                if profile_url in seen_urls:
                    continue
                seen_urls.add(profile_url)
                detail = session.get(profile_url, headers=DEFAULT_HEADERS, timeout=timeout, proxies=proxies)
                detail.raise_for_status()
                parsed = parse_resident_detail_html(
                    detail.text,
                    url=profile_url,
                    list_item=item,
                    http_status=detail.status_code,
                )
                results.append(parsed)
                if output:
                    write_results(output, results)
                if limit and len(results) >= limit:
                    return results
                if delay > 0:
                    time.sleep(delay)

            if not has_next_catalog_page(response.text):
                break
            page += 1
            if delay > 0:
                time.sleep(delay)

    return results


def load_snapshot(path: Path) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(rows, list):
        raise ValueError("Expected a JSON array")
    return [row for row in rows if isinstance(row, dict)]


def diff_snapshot_rows(old_rows: list[dict[str, Any]], new_rows: list[dict[str, Any]]) -> dict[str, Any]:
    def row_key(row: dict[str, Any]) -> str | None:
        return clean_unp(row.get("unp")) or clean_text(row.get("profile_url"))

    old_map = {key: row for row in old_rows if (key := row_key(row))}
    new_map = {key: row for row in new_rows if (key := row_key(row))}
    old_keys = set(old_map)
    new_keys = set(new_map)
    comparable_fields = (
        "name",
        "profile_url",
        "description",
        "city",
        "legal_address",
        "phone",
        "website",
        "activity_directions",
    )

    changed = []
    for key in sorted(old_keys & new_keys):
        field_changes = {}
        for field in comparable_fields:
            old_value = old_map[key].get(field)
            new_value = new_map[key].get(field)
            if old_value != new_value:
                field_changes[field] = {"old": old_value, "new": new_value}
        if field_changes:
            changed.append(
                {
                    "key": key,
                    "unp": clean_unp(new_map[key].get("unp")),
                    "name": new_map[key].get("name"),
                    "changes": field_changes,
                }
            )

    return {
        "old_count": len(old_map),
        "new_count": len(new_map),
        "added": [new_map[key] for key in sorted(new_keys - old_keys)],
        "removed": [old_map[key] for key in sorted(old_keys - new_keys)],
        "changed": changed,
    }


def import_pvt_snapshot_rows(db: Any, rows: list[dict[str, Any]], batch_size: int = 500) -> dict[str, int]:
    from app.database.models import Company

    stats = {"total": 0, "found_company": 0, "missing_company": 0, "invalid": 0, "saved": 0}
    pending = 0
    for row in rows:
        stats["total"] += 1
        unp = clean_unp(row.get("unp"))
        if not unp:
            stats["invalid"] += 1
            continue
        company = db.query(Company).filter(Company.unp == int(unp)).first()
        if not company:
            stats["missing_company"] += 1
            continue
        result = ParkResidentResult(
            unp=unp,
            status="found",
            name=clean_text(row.get("name")),
            profile_url=clean_text(row.get("profile_url")),
            description=clean_text(row.get("description")),
            source_url=clean_text(row.get("source_url")) or clean_text(row.get("profile_url")),
            city=clean_text(row.get("city")),
            legal_address=clean_text(row.get("legal_address")),
            phone=clean_text(row.get("phone")),
            website=clean_text(row.get("website")),
            activity_directions=row.get("activity_directions") if isinstance(row.get("activity_directions"), list) else None,
            list_letter=clean_text(row.get("list_letter")),
            list_page=row.get("list_page") if isinstance(row.get("list_page"), int) else None,
            list_description=clean_text(row.get("list_description")),
        )
        upsert_resident_record(db, company.id, result)
        stats["found_company"] += 1
        stats["saved"] += 1
        pending += 1
        if pending >= batch_size:
            db.commit()
            pending = 0
    if pending:
        db.commit()
    return stats


def import_pvt_snapshot_json(db: Any, snapshot_path: Path, batch_size: int = 500) -> dict[str, int]:
    return import_pvt_snapshot_rows(db, load_snapshot(snapshot_path), batch_size=batch_size)


def sync_pvt_residents_from_catalog(
    db: Any,
    output: Path | None = None,
    letters: Iterable[str] | None = None,
    limit: int | None = None,
    batch_size: int = 500,
    delay: float = 0.2,
    timeout: float = 30.0,
    proxy: str | None = None,
) -> dict[str, int]:
    rows = fetch_catalog_snapshot(
        output=output,
        letters=letters,
        delay=delay,
        timeout=timeout,
        proxy=proxy,
        limit=limit,
    )
    stats = import_pvt_snapshot_rows(
        db,
        [asdict(row) for row in rows],
        batch_size=batch_size,
    )
    stats["fetched"] = len(rows)
    stats["source"] = "catalog"
    if output:
        stats["output"] = str(output)
    return stats


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
    resume: bool = True,
) -> dict[str, int]:
    from app.database.models import Company, PVTResidentRecord

    stats = {"checked": 0, "found": 0, "not_found": 0, "invalid": 0, "error": 0, "saved": 0, "start_unp": 0, "last_unp": 0, "cursor_reset": 0}
    session = requests.Session()
    pending = 0
    checked_since_commit = 0
    remaining = limit
    cursor_unp = get_last_checked_unp(db) if resume and start_unp is None and offset == 0 else None
    last_unp: int | None = start_unp - 1 if start_unp is not None else cursor_unp
    stats["start_unp"] = int(last_unp or 0) + 1
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
                checked_since_commit += 1
                stats[result.status] = stats.get(result.status, 0) + 1
                if result.status == "found":
                    upsert_resident_record(db, company_id, result)
                    stats["saved"] += 1
                    pending += 1
                if checked_since_commit >= batch_size:
                    commit_pvt_cursor(db, last_unp)
                    pending = 0
                    checked_since_commit = 0
                logger.info("PVT resident check unp=%s status=%s", unp, result.status)
            except Exception as exc:
                commit_pvt_cursor(db, last_unp)
                pending = 0
                checked_since_commit = 0
                stats["checked"] += 1
                stats["error"] += 1
                logger.warning("PVT resident check failed unp=%s error=%s", unp, exc)
            if delay > 0:
                time.sleep(delay)

        if remaining is not None:
            remaining -= len(rows)
        if len(rows) < page_size:
            break

    if pending or checked_since_commit:
        commit_pvt_cursor(db, last_unp)
    stats["last_unp"] = int(last_unp or 0)

    if last_unp is not None:
        has_more = db.query(Company.id).filter(Company.unp > last_unp).first() is not None
        if not has_more and resume and start_unp is None and offset == 0:
            commit_pvt_cursor(db, None)
            stats["cursor_reset"] = 1
    return stats
