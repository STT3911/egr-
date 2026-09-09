"""Authenticated export client for service.court.gov.by court judgments."""

from __future__ import annotations

import hashlib
import html
import math
import os
import random
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

import requests


BASE_URL = "https://service.court.gov.by"
SEARCH_PATH = "/ru/juridical/judgmentresults/search"
SEARCH_PAGE_PATH = "/ru/juridical/judgmentresults/searchpage"
REFERER_PATH = "/ru/juridical/judgmentresults"

COURTS: Dict[int, str] = {
    151: "Экономический суд Брестской области",
    152: "Экономический суд Витебской области",
    153: "Экономический суд Гомельской области",
    154: "Экономический суд Гродненской области",
    155: "Экономический суд г. Минска",
    156: "Экономический суд Минской области",
    157: "Экономический суд Могилевской области",
    1: "Судебная коллегия по экономическим делам Верховного Суда",
}


class CourtAuthenticationError(RuntimeError):
    """The supplied ASP.NET session is absent or no longer valid."""


def normalize_cookie_header(value: str) -> str:
    """Accept a copied Cookie label, but reject unrelated headers or controls."""
    value = value.lstrip("\ufeff").strip()
    value = re.sub(r"^cookie\s*:\s*", "", value, count=1, flags=re.I)
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if lines and lines[0].lower() == "cookie":
        lines.pop(0)
    if len(lines) != 1 or any(ord(char) < 32 for char in lines[0]):
        raise ValueError("Cookie file must contain one Cookie value (optional Cookie label)")
    return lines[0]


@dataclass(frozen=True)
class CourtSearchFilters:
    date_from: str
    date_to: str
    court: int
    type_proc: int = 14
    category_dispute: int = 0
    type_dispute: int = 0
    num_suit: str = ""
    name: str = ""

    def search_form(self) -> Dict[str, str]:
        return {
            "NumSuit": self.num_suit,
            "Name": self.name,
            "Court": str(self.court),
            "CategoryDisput": str(self.category_dispute),
            "TypeDispute": str(self.type_dispute),
            "DateFrom": self.date_from,
            "DateTo": self.date_to,
            "TypeProc": str(self.type_proc),
        }

    def page_query(self, page: int) -> Dict[str, str]:
        # The MVC searchpage action returns an empty body when empty/default
        # form fields are repeated in the query string. Match the URL emitted
        # by the site's own pagination JavaScript and add optional filters only
        # when they are active.
        query = {
            "Court": str(self.court),
            "TypeProc": str(self.type_proc),
            "DateFrom": self.date_from,
            "DateTo": self.date_to,
            "SortColumn": "dateDoc",
            "SortOrder": "desc",
            "NumberPage": "1",
            "CountRecords": "10",
            "page": str(page),
        }
        if self.num_suit:
            query["NumSuit"] = self.num_suit
        if self.name:
            query["Name"] = self.name
        if self.category_dispute:
            query["CategoryDisput"] = str(self.category_dispute)
        if self.type_dispute:
            query["TypeDispute"] = str(self.type_dispute)
        return query


@dataclass(frozen=True)
class CourtJudgment:
    key: str
    court_id: int
    court: str
    case_number: str
    document_type: str
    judgment_date: Optional[str]
    resolution: str
    download_url: Optional[str]
    process_id: Optional[str]
    document_id: Optional[str]
    source_page: int

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


def _clean_text(fragment: str) -> str:
    fragment = re.sub(r"(?is)<script\b.*?</script>", " ", fragment)
    fragment = re.sub(r"(?is)<style\b.*?</style>", " ", fragment)
    fragment = re.sub(r"(?i)<br\s*/?>|</p\s*>", "\n", fragment)
    fragment = re.sub(r"(?s)<[^>]+>", " ", fragment)
    fragment = html.unescape(fragment).replace("\xa0", " ")
    lines = [re.sub(r"\s+", " ", line).strip() for line in fragment.splitlines()]
    return "\n".join(line for line in lines if line)


def _class_content(fragment: str, tag: str, class_name: str) -> Optional[str]:
    pattern = re.compile(
        rf"(?is)<{tag}\b[^>]*class=[\"'][^\"']*\b{re.escape(class_name)}\b"
        rf"[^\"']*[\"'][^>]*>(.*?)</{tag}>",
    )
    match = pattern.search(fragment)
    return match.group(1) if match else None


def _normalize_date(value: str) -> Optional[str]:
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d.%m.%Y").date().isoformat()
    except ValueError:
        return value


def _judgment_key(
    document_id: Optional[str],
    process_id: Optional[str],
    court_id: int,
    case_number: str,
    judgment_date: Optional[str],
) -> str:
    if document_id:
        return f"document:{document_id}"
    if process_id:
        return f"process:{process_id}"
    raw = "|".join((str(court_id), case_number, judgment_date or ""))
    return "fallback:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_search_results(
    response_html: str,
    *,
    court_id: int,
    source_page: int,
) -> Tuple[List[CourtJudgment], int]:
    """Parse one HTML result fragment and return records plus total page count."""

    page_numbers = [
        int(value)
        for value in re.findall(r"data-page=[\"'](\d+)[\"']", response_html)
    ]
    total_pages = max(page_numbers, default=1)
    records: List[CourtJudgment] = []

    for fragment in re.split(r"(?i)<hr\s*/?>", response_html):
        heading_html = _class_content(fragment, "span", "number")
        if heading_html is None:
            continue

        heading = _clean_text(heading_html)
        heading_match = re.match(r"(?is)^Дело\s*№?\s*(.*?)\s*,\s*(.+)$", heading)
        if heading_match:
            case_number = heading_match.group(1).strip()
            court_name = heading_match.group(2).strip()
        else:
            case_number = heading
            court_name = COURTS.get(court_id, "")

        text_blocks = re.findall(
            r"(?is)<div\b[^>]*class=[\"'][^\"']*\btext\b[^\"']*[\"'][^>]*>"
            r"(.*?)</div>",
            fragment,
        )
        document_type = ""
        if text_blocks:
            type_html = _class_content(text_blocks[0], "p", "result")
            if type_html is not None:
                document_type = _clean_text(type_html)

        date_html = _class_content(fragment, "p", "date-result")
        judgment_date = _normalize_date(_clean_text(date_html or ""))

        resolution_match = re.search(
            r"(?is)<div\b[^>]*class=[\"'][^\"']*\breadmore\b[^\"']*"
            r"\bresult\b[^\"']*[\"'][^>]*>(.*?)</div>",
            fragment,
        )
        resolution = _clean_text(resolution_match.group(1) if resolution_match else "")
        resolution = re.sub(r"(?:\n|^)Скачать\s*$", "", resolution).strip()

        download_match = re.search(
            r"href=[\"']([^\"']*judgmentresults/downloadresolution[^\"']*)[\"']",
            fragment,
            re.IGNORECASE,
        )
        download_url = None
        process_id = None
        document_id = None
        if download_match:
            download_url = urljoin(BASE_URL, html.unescape(download_match.group(1)))
            query = parse_qs(urlparse(download_url).query)
            process_id = (query.get("processId") or [None])[0]
            document_id = (query.get("docId") or [None])[0]

        records.append(
            CourtJudgment(
                key=_judgment_key(
                    document_id,
                    process_id,
                    court_id,
                    case_number,
                    judgment_date,
                ),
                court_id=court_id,
                court=court_name,
                case_number=case_number,
                document_type=document_type,
                judgment_date=judgment_date,
                resolution=resolution,
                download_url=download_url,
                process_id=process_id,
                document_id=document_id,
                source_page=source_page,
            )
        )

    return records, total_pages


class CourtJudgmentClient:
    def __init__(
        self,
        cookie_header: str,
        *,
        timeout: Tuple[float, float] = (10.0, 60.0),
        cookie_file: Optional[Path] = None,
        rate_limit_state_file: Optional[Path] = None,
        min_interval_seconds: float = 600.0,
        delay_jitter_seconds: float = 120.0,
    ) -> None:
        cookie_header = normalize_cookie_header(cookie_header)
        if not cookie_header:
            raise ValueError("Court cookie header is empty")
        if not math.isfinite(min_interval_seconds) or min_interval_seconds < 600:
            raise ValueError("min_interval_seconds must be at least 600")
        if not math.isfinite(delay_jitter_seconds) or delay_jitter_seconds < 0:
            raise ValueError("delay_jitter_seconds must be finite and nonnegative")

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "*/*",
                "Origin": BASE_URL,
                "Referer": urljoin(BASE_URL, REFERER_PATH),
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/152 Safari/537.36"
                ),
                "X-Requested-With": "XMLHttpRequest",
            }
        )
        parsed = SimpleCookie()
        parsed.load(cookie_header)
        if not parsed:
            raise ValueError("Court cookie header could not be parsed")
        for name, morsel in parsed.items():
            self.session.cookies.set(
                name,
                morsel.value,
                domain="service.court.gov.by",
                path="/",
            )

        self.timeout = timeout
        self.cookie_file = cookie_file
        self.rate_limit_state_file = rate_limit_state_file
        self.min_interval_seconds = min_interval_seconds
        self.delay_jitter_seconds = delay_jitter_seconds
        self._last_request_started = self._load_last_request_started()

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "CourtJudgmentClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _load_last_request_started(self) -> Optional[float]:
        if self.rate_limit_state_file is None or not self.rate_limit_state_file.exists():
            return None
        try:
            timestamp = float(self.rate_limit_state_file.read_text(encoding="ascii").strip())
            if not math.isfinite(timestamp) or timestamp < 0:
                raise ValueError("Invalid timestamp")
            return timestamp
        except (OSError, ValueError) as exc:
            raise ValueError("Cannot safely read court request timestamp; check rate state file") from exc

    def _save_last_request_started(self) -> None:
        if self.rate_limit_state_file is None or self._last_request_started is None:
            return
        self.rate_limit_state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.rate_limit_state_file.with_suffix(
            self.rate_limit_state_file.suffix + ".tmp"
        )
        temporary.write_text(f"{self._last_request_started:.6f}\n", encoding="ascii")
        os.replace(temporary, self.rate_limit_state_file)

    def _wait_for_request_slot(self) -> None:
        if self._last_request_started is None:
            return
        interval = self.min_interval_seconds + random.uniform(
            0.0,
            self.delay_jitter_seconds,
        )
        remaining = interval - (time.time() - self._last_request_started)
        if remaining > 0:
            time.sleep(remaining)

    def _persist_cookies(self) -> None:
        if self.cookie_file is None:
            return
        cookies = [
            cookie
            for cookie in self.session.cookies
            if not cookie.is_expired()
            and (
                not cookie.domain
                or cookie.domain.lstrip(".") == "service.court.gov.by"
            )
        ]
        if not cookies:
            return
        value = "; ".join(f"{cookie.name}={cookie.value}" for cookie in cookies)
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cookie_file.with_suffix(self.cookie_file.suffix + ".tmp")
        temporary.write_text(value + "\n", encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, self.cookie_file)

    def _request(self, method: str, url: str, **kwargs: object) -> requests.Response:
        parsed_url = urlparse(url)
        if (parsed_url.scheme != "https" or parsed_url.netloc != "service.court.gov.by"):
            raise ValueError("Court requests must target the original HTTPS host")
        kwargs["allow_redirects"] = False
        self._wait_for_request_slot()
        self._last_request_started = time.time()
        self._save_last_request_started()
        response = self.session.request(method, url, **kwargs)
        # ASP.NET Forms Authentication can renew a sliding session through
        # Set-Cookie. Requests updates the jar before this point; persist it so
        # the next process can resume with the renewed values.
        self._persist_cookies()
        return self._checked_response(response)

    def _checked_response(self, response: requests.Response) -> requests.Response:
        location = response.headers.get("Location", "")
        requires_auth = response.headers.get("REQUIRES_AUTH") == "1"
        if (
            response.status_code in (301, 302, 303, 307, 308)
            and "/Account/Login" in location
        ) or requires_auth:
            raise CourtAuthenticationError(
                "Court session expired; refresh the local cookie file and resume"
            )
        if response.status_code in (401, 403):
            raise CourtAuthenticationError("Court access denied; verify account access before resuming")
        if 300 <= response.status_code < 400:
            raise RuntimeError("Unexpected court redirect; export stopped")
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        login_page = False
        if "text/html" in content_type:
            login_page = "action=\"/Account/Login" in response.text
        if "/Account/Login" in response.url or login_page:
            raise CourtAuthenticationError(
                "Court session expired; refresh the local cookie file and resume"
            )
        return response

    def fetch_page(
        self,
        filters: CourtSearchFilters,
        page: int,
    ) -> Tuple[List[CourtJudgment], int]:
        if page < 1:
            raise ValueError("page must be at least 1")
        if page == 1:
            response = self._request(
                "POST",
                urljoin(BASE_URL, SEARCH_PATH),
                data=filters.search_form(),
                timeout=self.timeout,
                allow_redirects=False,
            )
        else:
            response = self._request(
                "GET",
                urljoin(BASE_URL, SEARCH_PAGE_PATH),
                params=filters.page_query(page),
                timeout=self.timeout,
                allow_redirects=False,
            )
        records, pages = parse_search_results(
            response.text,
            court_id=filters.court,
            source_page=page,
        )
        if not records and (page > 1 or "searchResultPage" not in response.text):
            raise RuntimeError("Empty or unrecognized court response; page was not completed")
        return records, pages

    def download_document(self, url: str, destination: Path) -> Path:
        response = self._request(
            "GET",
            url,
            timeout=self.timeout,
            allow_redirects=False,
            stream=True,
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(destination.suffix + ".partial")
        with partial.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 128):
                if chunk:
                    handle.write(chunk)
        partial.replace(destination)
        return destination


def iter_court_filters(
    court_ids: Iterable[int],
    *,
    date_from: str,
    date_to: str,
    type_proc: int,
    category_dispute: int,
    type_dispute: int,
) -> Iterable[CourtSearchFilters]:
    for court_id in court_ids:
        if court_id not in COURTS:
            raise ValueError(f"Unknown court id: {court_id}")
        yield CourtSearchFilters(
            date_from=date_from,
            date_to=date_to,
            court=court_id,
            type_proc=type_proc,
            category_dispute=category_dispute,
            type_dispute=type_dispute,
        )
