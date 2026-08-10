"""Public leadership observations from the Minsk labour committee website.

The committee publishes dated occupational-safety examination lists with a
person's name, position, and employer, but without a UNP. This module keeps the
source semantics intact: every row is stored as historical evidence and only
an unambiguous exact normalized company-name match receives a company/UNP link.
"""

from __future__ import annotations

import hashlib
import html
import re
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.logger import get_logger
from app.database.models import Company, CompanyLeadershipObservation, CompanyNameHistory
from app.utils.search_normalizer import normalize_company_name


logger = get_logger("minsk_leadership")

BASE_URL = "https://komtrud.minsk.gov.by"
SEARCH_URL = f"{BASE_URL}/search/index.php"
CHECK_KNOWLEDGE_URL = (
    f"{BASE_URL}/examination/labor_protection/check_knowledge.php"
)
SEARCH_PHRASE = "Список руководителей и специалистов для прохождения проверки знаний"
SOURCE_NAME = "komtrud_minsk_labor_safety"

# Confirmed historical pages are retained as seeds because the site's own
# search index is incomplete and old pages may disappear from its top results.
KNOWN_SOURCE_URLS = (
    f"{BASE_URL}/news/detail.php?ID=6764",
    f"{BASE_URL}/news/detail.php?ID=6794",
    f"{BASE_URL}/news/detail.php?ID=7002",
    (
        f"{BASE_URL}/examination/labor_protection/"
        "20250123-spisok-rukovoditeley.php"
    ),
)

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "User-Agent": "Tendex-EGR/1.0 (+https://test.tendex.by)",
}


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or "")).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _canonical_source_url(value: str) -> str | None:
    absolute = urljoin(BASE_URL, html.unescape(value or ""))
    parts = urlsplit(absolute)
    if parts.scheme not in {"http", "https"} or parts.netloc != "komtrud.minsk.gov.by":
        return None

    path = re.sub(r"/{2,}", "/", parts.path)
    if path == "/news/detail.php":
        query = dict(parse_qsl(parts.query, keep_blank_values=False))
        page_id = query.get("ID")
        if not page_id or not page_id.isdigit():
            return None
        return urlunsplit(("https", parts.netloc, path, urlencode({"ID": page_id}), ""))

    if path.startswith("/examination/labor_protection/") and path.endswith(".php"):
        return urlunsplit(("https", parts.netloc, path, "", ""))

    return None


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._href = href
                self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, clean_text(" ".join(self._chunks))))
            self._href = None
            self._chunks = []


@dataclass(frozen=True)
class ParsedLeadershipRow:
    source_row_no: int
    person_name: str
    position: str
    organization_name: str
    exam_type: str | None
    event_date: date | None
    source_title: str
    source_url: str
    is_head: bool


class _LeadershipTableParser(HTMLParser):
    """Parse numeric five-column rows, including pages with nested layout tables."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.rows: list[list[str]] = []
        self._title_chunks: list[str] = []
        self._in_title = False
        self._skip_depth = 0
        self._row_stack: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = True
        elif tag == "tr":
            self._row_stack.append({"cells": [], "cell": None})
        elif tag in {"td", "th"} and self._row_stack:
            self._row_stack[-1]["cell"] = []
        elif tag == "br" and self._row_stack and self._row_stack[-1]["cell"] is not None:
            self._row_stack[-1]["cell"].append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self._title_chunks.append(data)
        if self._row_stack and self._row_stack[-1]["cell"] is not None:
            self._row_stack[-1]["cell"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
            self.title = clean_text(" ".join(self._title_chunks))
        elif tag in {"td", "th"} and self._row_stack:
            row = self._row_stack[-1]
            if row["cell"] is not None:
                row["cells"].append(clean_text(" ".join(row["cell"])))
                row["cell"] = None
        elif tag == "tr" and self._row_stack:
            row = self._row_stack.pop()
            if row["cells"]:
                self.rows.append(row["cells"])


def _event_date_from_title(title: str) -> date | None:
    matches = re.findall(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", title or "")
    if not matches:
        return None
    day, month, year = matches[-1]
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def is_organization_head(position: str) -> bool:
    """Conservatively identify roles that denote the organization's head."""
    value = clean_text(position).lower().replace("ё", "е")
    value = re.sub(r"[–—−]", "-", value)

    if re.search(r"\b(заместител|помощник|первый заместитель)\b", value):
        return False
    if re.search(
        r"\bдиректор\s+(по|ресторана|магазина|филиала|представительства|департамента|направления)\b",
        value,
    ):
        return False

    if re.fullmatch(r"(?:генеральный\s+|исполнительный\s+)?директор", value):
        return True
    if re.match(
        r"^(?:генеральный\s+)?директор\s+(?:ооо|одо|зао|оао|чуп|уп|"
        r"общество\b|предприятие\b|учреждение\b)",
        value,
    ):
        return True
    if re.fullmatch(r"председатель(?:\s+правления)?", value):
        return True
    if re.fullmatch(r"управляющий", value):
        return True
    if re.fullmatch(r"руководитель(?:\s+организации)?", value):
        return True
    if re.fullmatch(r"индивидуальный предприниматель", value):
        return True
    return False


def parse_leadership_page(page_html: str, source_url: str) -> list[ParsedLeadershipRow]:
    parser = _LeadershipTableParser()
    parser.feed(page_html)
    title = parser.title
    event_date = _event_date_from_title(title)
    parsed: list[ParsedLeadershipRow] = []

    for cells in parser.rows:
        if len(cells) < 5:
            continue
        row_number = cells[0].strip().rstrip(".)")
        if not row_number.isdigit():
            continue
        person_name, position, organization_name = map(clean_text, cells[1:4])
        exam_type = clean_text(cells[4]) or None
        if len(person_name.split()) < 2 or not position or not organization_name:
            continue
        parsed.append(
            ParsedLeadershipRow(
                source_row_no=int(row_number),
                person_name=person_name,
                position=position,
                organization_name=organization_name,
                exam_type=exam_type,
                event_date=event_date,
                source_title=title,
                source_url=source_url,
                is_head=is_organization_head(position),
            )
        )
    return parsed


def _get(session: requests.Session, url: str, *, timeout: float, retries: int) -> str:
    last_error: Exception | None = None
    for attempt in range(1, retries + 2):
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            if attempt <= retries:
                time.sleep(float(attempt))
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def discover_source_urls(
    session: requests.Session,
    *,
    timeout: float = 30.0,
    retries: int = 2,
) -> list[str]:
    urls = set(KNOWN_SOURCE_URLS)
    urls.add(CHECK_KNOWLEDGE_URL)
    search_query = urlencode({"q": SEARCH_PHRASE, "how": "d"})
    try:
        search_html = _get(
            session,
            f"{SEARCH_URL}?{search_query}",
            timeout=timeout,
            retries=retries,
        )
    except RuntimeError as exc:
        # Site search is only a discovery aid. Confirmed seed pages must still
        # be refreshed when the search index or endpoint is temporarily down.
        logger.warning("Minsk leadership source discovery failed: %s", exc)
        return sorted(urls)

    parser = _LinkParser()
    parser.feed(search_html)
    for href, label in parser.links:
        if "список руководителей и специалистов" not in label.lower():
            continue
        canonical = _canonical_source_url(href)
        if canonical:
            urls.add(canonical)
    return sorted(urls)


def _unique_company_matches(
    candidate_rows: Iterable[tuple[str, Any, int]],
) -> dict[str, tuple[Any, int]]:
    grouped: dict[str, set[tuple[Any, int]]] = {}
    for normalized_name, company_id, unp in candidate_rows:
        if normalized_name:
            grouped.setdefault(normalized_name, set()).add((company_id, int(unp)))
    return {
        normalized_name: next(iter(companies))
        for normalized_name, companies in grouped.items()
        if len(companies) == 1
    }


def resolve_company_matches(
    db: Any,
    normalized_names: set[str],
    *,
    batch_size: int = 500,
) -> dict[str, tuple[Any, int]]:
    candidate_rows: list[tuple[str, Any, int]] = []
    names = sorted(name for name in normalized_names if name)
    for offset in range(0, len(names), batch_size):
        batch = names[offset : offset + batch_size]
        candidate_rows.extend(
            db.query(CompanyNameHistory.search_name, Company.id, Company.unp)
            .join(Company, Company.id == CompanyNameHistory.company_id)
            .filter(CompanyNameHistory.search_name.in_(batch))
            .all()
        )
    return _unique_company_matches(candidate_rows)


def _sync_key(row: ParsedLeadershipRow) -> str:
    canonical = "\x1f".join(
        [
            row.source_url,
            row.person_name.lower(),
            row.position.lower(),
            row.organization_name.lower(),
            row.event_date.isoformat() if row.event_date else "",
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def import_observations(
    db: Any,
    rows: Iterable[ParsedLeadershipRow],
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    materialized = list(rows)
    normalized_by_org = {
        row.organization_name: normalize_company_name(row.organization_name) or ""
        for row in materialized
    }
    matches = resolve_company_matches(db, set(normalized_by_org.values()))
    now = datetime.utcnow()
    payloads: list[dict[str, Any]] = []
    stats = {
        "rows": len(materialized),
        "head_rows": 0,
        "matched_rows": 0,
        "matched_head_rows": 0,
        "unmatched_head_rows": 0,
        "saved": 0,
    }

    for row in materialized:
        normalized_name = normalized_by_org[row.organization_name]
        match = matches.get(normalized_name)
        company_id, unp = match if match else (None, None)
        if row.is_head:
            stats["head_rows"] += 1
        if match:
            stats["matched_rows"] += 1
            if row.is_head:
                stats["matched_head_rows"] += 1
        elif row.is_head:
            stats["unmatched_head_rows"] += 1

        payloads.append(
            {
                "company_id": company_id,
                "unp": unp,
                "person_name": row.person_name,
                "position": row.position,
                "organization_name": row.organization_name,
                "organization_name_norm": normalized_name or None,
                "is_head": row.is_head,
                "event_date": row.event_date,
                "exam_type": row.exam_type,
                "source_name": SOURCE_NAME,
                "source_title": row.source_title,
                "source_url": row.source_url,
                "source_row_no": row.source_row_no,
                "match_method": "exact_normalized_name" if match else None,
                "match_confidence": 1.0 if match else None,
                "raw_json": {
                    **asdict(row),
                    "event_date": row.event_date.isoformat() if row.event_date else None,
                },
                "sync_key": _sync_key(row),
                "last_seen_at": now,
                "updated_at": now,
            }
        )

    if dry_run or not payloads:
        return stats

    unique_payloads = {payload["sync_key"]: payload for payload in payloads}
    stmt = pg_insert(CompanyLeadershipObservation).values(list(unique_payloads.values()))
    excluded = stmt.excluded
    stmt = stmt.on_conflict_do_update(
        constraint="uq_company_leadership_observations_sync_key",
        set_={
            "company_id": excluded.company_id,
            "unp": excluded.unp,
            "person_name": excluded.person_name,
            "position": excluded.position,
            "organization_name": excluded.organization_name,
            "organization_name_norm": excluded.organization_name_norm,
            "is_head": excluded.is_head,
            "event_date": excluded.event_date,
            "exam_type": excluded.exam_type,
            "source_title": excluded.source_title,
            "source_row_no": excluded.source_row_no,
            "match_method": excluded.match_method,
            "match_confidence": excluded.match_confidence,
            "raw_json": excluded.raw_json,
            "last_seen_at": excluded.last_seen_at,
            "updated_at": excluded.updated_at,
        },
    )
    db.execute(stmt)
    db.commit()
    stats["saved"] = len(unique_payloads)
    return stats


def sync_minsk_leadership(
    db: Any,
    *,
    timeout: float = 30.0,
    retries: int = 2,
    delay: float = 0.25,
    dry_run: bool = False,
) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    try:
        urls = discover_source_urls(session, timeout=timeout, retries=retries)
        rows: list[ParsedLeadershipRow] = []
        page_stats: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for index, url in enumerate(urls):
            if index:
                time.sleep(delay)
            try:
                page_html = _get(session, url, timeout=timeout, retries=retries)
                page_rows = parse_leadership_page(page_html, url)
                rows.extend(page_rows)
                page_stats.append({"url": url, "rows": len(page_rows)})
            except RuntimeError as exc:
                logger.warning("Minsk leadership page failed: %s", exc)
                errors.append({"url": url, "error": str(exc)})

        import_stats = import_observations(db, rows, dry_run=dry_run)
        return {
            "status": "partial" if errors else "ok",
            "source": SOURCE_NAME,
            "discovered_pages": len(urls),
            "parsed_pages": len(page_stats),
            "pages": page_stats,
            "errors": errors,
            "import": import_stats,
            "dry_run": dry_run,
        }
    finally:
        session.close()
