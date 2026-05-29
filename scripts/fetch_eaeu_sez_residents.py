"""Fetch EAEU SEZ resident companies from portal.eaeunion.org.

The public registry page renders its table through the CDAC XML broker. This
script walks all broker pages and stores rows for the requested country.

Examples:
  python scripts/fetch_eaeu_sez_residents.py
  python scripts/fetch_eaeu_sez_residents.py --output data/eaeu/sez_belarus.json --csv data/eaeu/sez_belarus.csv
  python scripts/fetch_eaeu_sez_residents.py --country Беларусь --limit-pages 2
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE_URL = "https://portal.eaeunion.org"
BROKER_URL = (
    "https://portal.eaeunion.org/sites/odata/"
    "_layouts/CDAC.Web/XmlSourceBrockerService.asmx/getViewXmlContentFriendly"
)
VIEW_NAME = "regui.SPLIST_TABLE_VIEW"
DATA_LIST_ID = "52f4aa59-13c3-4807-a53f-cc5f54d65f9a"
VIEW_ID = "58d4437f-dd0e-45fa-99e3-6e15ea62b49e"
ITEM_URL = "/sites/odata/_layouts/15/Portal.EEC.Registry.UI/DisplayForm.aspx"

FIELD_ALIASES = {
    "_X0421__X0442__X0440__X0430__X043D__X0430__": "country",
    "TMP_REGISTERSEZRESIDENTSDETAIL_NAME": "full_name",
    "TMP_REGISTERSEZRESIDENTSDETAIL_SHORTNAME": "short_name",
    "_X042E__X0440__X0438__X0434__X0438__X0447__X0435__X0441__X043A__X0438__X0439__X0020__X0430__X0434__X0440__X0435__X002C__X0020__X043C__X0435__X0441__X0442__X043E__X0020__X0436__X0438__X0442__X0435__X043B__X044C__X0441__X0442__X0432__X0430_": "legal_address",
    "TMP_REGISTERSEZRESIDENTSDETAIL_FIRMNAME": "firm_name",
    "TMP_REGISTERSEZRESIDENTSDETAIL_INN": "tax_id",
    "TMP_REGISTERSEZRESIDENTSDETAIL_NAMEAGENCY": "registration_agency",
    "TMP_REGISTERSEZRESIDENTSDETAIL_NAMESEZ": "sez_name",
    "TMP_REGISTERSEZRESIDENTSDETAIL_NAMEPROJECT": "project_name",
    "_X0414__X0430__X0442__X0430__X0020__X0432__X043D__X0435__X0441__X0435__X043D__X0438__X044F__X0020__X0437__X0430__X043F__X0438__X0441__X0438__X0020__X0432__X0020__X0440__X0435__X0435__X0441__X0442__X0440__X0020__X0440__X0435__X0437__X0438__X0434__X0435__X043D__X0442__X043E__X0432__X0020__X0421__X042D__X0417__X0020__X0433__X043E__X0441__X0443__X0434__X0430__X0440__X0441__X0442__X0432__X0430__X002D__X0447__X043B__X0435__X043D__X0430__X0020__X0422__X0430__X043C__X043E__X0436__X0435__X043D__X043D__X043E__X0433__X043E__X0020__X0441__X043E__X044E__X0437__X0430__X0020__X043E__X0020__X0440__X0435__X0433__X0438__X0441__X0442__X0440__X0430__X0446__X0438__X0438__X0020__X043B__X0438__X0446__X0430__X0020__X0432__X0020__X043A__X0430__X0447__X0435__X0441__X0442__X0432__X0435__X0020__X0440__X0435__X0437__X0438__X0434__X0435__X043D__X0442__X0430__X0020__X0028__X0443__X0447__X0430__X0441__X0442__X043D__X0438__X043A__X0430__X0029__X0020__X0421__X042D__X0417__X0020__X0438__X043B__X0438__X0020__X043E__X0020__X043B__X0438__X0448__X0435__X043D__X0438__X0438__X0020__X043B__X0438__X0446__X0430__X0020__X0441__X0442__X0430__X0442__X0443__X0441__X0430__X0020__X0440__X0435__X0437__X0438__X0434__X0435__X0442__X0430__X0020__X0028__X0020__X0443__X0447__X0430__X0441__X0442__X043D__X0438__X043A__X0430__X0020__X0029__X0020__X0421__X042D__X0417_": "registry_entry_date",
    "TMP_REGISTERSEZRESIDENTSDETAIL_CERTIFICATE": "certificate",
}

TITLE_ALIASES = {
    "Страна": "country",
    "Полное наименование юридического лица с указанием организа-ционно-правовой": "full_name",
    "Сокращенное наименование юридического лица": "short_name",
    "Юридический адрес, место жительства": "legal_address",
    "Фирменное наименование юридического лица (при наличии)": "firm_name",
    "ИНН/УНП/РНН (БИН)": "tax_id",
    "Наименование органа осуществившего регистрацию лица в качестве резидента (участника) СЭЗ": "registration_agency",
    "Наименование СЭЗ, на территории которой резидент (участник) СЭЗ осуществляет деятельность": "sez_name",
    "Наименование проекта, осуществляемого резидентом (участником) СЭЗ в соответствии с заключенным соглашением об осуществлении деятельности на территории СЭЗ": "project_name",
    "Дата внесения записи в реестр резидентов СЭЗ государства-члена Таможенного союза о регистрации лица в качестве резидента (участника) СЭЗ или о лишении лица статуса резидента ( участника ) СЭЗ": "registry_entry_date",
    "Серия и номер свидетельства, удостоверяющего регистрацию лица в качестве резидента (участника) СЭЗ (при наличии)": "certificate",
}

OUTPUT_FIELDS = [
    "item_id",
    "source_url",
    "country",
    "full_name",
    "short_name",
    "legal_address",
    "firm_name",
    "tax_id",
    "registration_agency",
    "sez_name",
    "project_name",
    "registry_entry_date",
    "certificate",
]


def normalize_text(value: str) -> str:
    value = html.unescape(value or "")
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value.replace(" Посмотреть на карте", "").strip()


def item_id_from_href(href: str | None) -> int | None:
    if not href:
        return None
    match = re.search(r"[?&]ItemId=(\d+)", html.unescape(href), re.IGNORECASE)
    return int(match.group(1)) if match else None


@dataclass
class ParsedPage:
    rows: list[dict[str, Any]]
    next_params: dict[str, str] | None
    overall_count: int | None


class RegistryTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headers: dict[str, str] = {}
        self.rows: list[dict[str, Any]] = []
        self.next_params: dict[str, str] | None = None
        self.overall_count: int | None = None
        self._current_row: dict[str, Any] | None = None
        self._current_cell: tuple[str, list[str]] | None = None
        self._current_header: tuple[str, list[str]] | None = None
        self._in_overall_count = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {name: value or "" for name, value in attrs}
        if tag == "tr" and "data-href" in attrs_dict:
            href = html.unescape(attrs_dict["data-href"])
            self._current_row = {
                "source_url": urljoin(BASE_URL, href),
                "item_id": item_id_from_href(href),
            }
        elif tag == "td" and self._current_row is not None:
            self._current_cell = (attrs_dict.get("name", ""), [])
        elif tag == "th" and attrs_dict.get("name"):
            self._current_header = (attrs_dict["name"], [])
        elif tag == "a" and attrs_dict.get("id") == "PageLinkNext":
            data_params = html.unescape(attrs_dict.get("data-params", ""))
            parsed = parse_qs(data_params, keep_blank_values=True)
            self.next_params = {
                key: values[-1]
                for key, values in parsed.items()
                if values and key in {"paginginfo", "pagenumber"}
            }
        elif tag == "div" and "cr-hidden-overallcount" in attrs_dict.get("class", ""):
            self._in_overall_count = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "th" and self._current_header is not None:
            name, chunks = self._current_header
            self.headers[name] = normalize_text(" ".join(chunks))
            self._current_header = None
        elif tag == "td" and self._current_cell is not None and self._current_row is not None:
            name, chunks = self._current_cell
            title = self.headers.get(name, name)
            key = FIELD_ALIASES.get(name) or TITLE_ALIASES.get(title) or title
            self._current_row[key] = normalize_text(" ".join(chunks))
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            self.rows.append(self._current_row)
            self._current_row = None
        elif tag == "div" and self._in_overall_count:
            self._in_overall_count = False

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell[1].append(data)
        elif self._current_header is not None:
            self._current_header[1].append(data)
        elif self._in_overall_count:
            text = normalize_text(data)
            self.overall_count = int(text) if text.isdigit() else None


def build_parameters(extra: dict[str, Any] | None = None) -> str:
    params = {
        "list": DATA_LIST_ID,
        "view": VIEW_ID,
        "itemUrl": ITEM_URL,
    }
    if extra:
        params.update({key: value for key, value in extra.items() if value not in (None, "")})

    root = ET.Element("p")
    for name, value in params.items():
        ET.SubElement(root, "parameter", {"name": name, "value": str(value)})
    return ET.tostring(root, encoding="unicode", short_empty_elements=True)


def caml_text_eq(field_name: str, value: str) -> str:
    return (
        "<Eq>"
        f"<FieldRef Name=\"{field_name}\"/>"
        f"<Value Type=\"Text\"><![CDATA[{value}]]></Value>"
        "</Eq>"
    )


def caml_state_on(on_date: date) -> str:
    iso_date = datetime.combine(on_date, datetime.min.time()).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return (
        "<And>"
        "<Or>"
        "<Leq>"
        "<FieldRef Name='StartDate'/>"
        f"<Value Type='DateTime' IncludeTimeValue='False'>{iso_date}</Value>"
        "</Leq>"
        "<IsNull><FieldRef Name='StartDate'/></IsNull>"
        "</Or>"
        "<Or>"
        "<Geq>"
        "<FieldRef Name='EndDate'/>"
        f"<Value Type='DateTime' IncludeTimeValue='False'>{iso_date}</Value>"
        "</Geq>"
        "<IsNull><FieldRef Name='EndDate'/></IsNull>"
        "</Or>"
        "</And>"
    )


def join_caml(left: str, right: str) -> str:
    if left and right:
        return f"<And>{left}{right}</And>"
    return left or right


def extract_html_fragment(response_text: str) -> str:
    root = ET.fromstring(response_text)
    error = root.find(".//Error")
    if error is not None:
        raise RuntimeError(error.get("message") or "".join(error.itertext()) or "CDAC service error")
    return root.text or ""


def fetch_page(
    session: requests.Session,
    page_params: dict[str, str] | None,
    timeout: float,
    retries: int,
) -> ParsedPage:
    last_error: Exception | None = None
    for attempt in range(1, retries + 2):
        try:
            response = session.post(
                BROKER_URL,
                data={
                    "viewName": VIEW_NAME,
                    "parameters": build_parameters(page_params),
                },
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "X-CDAC-LOCALE": "ru-ru",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                },
                timeout=timeout,
            )
            response.raise_for_status()
            parser = RegistryTableParser()
            parser.feed(extract_html_fragment(response.text))
            return ParsedPage(parser.rows, parser.next_params, parser.overall_count)
        except (requests.RequestException, ET.ParseError, RuntimeError) as exc:
            last_error = exc
            if attempt > retries:
                break
            time.sleep(min(2 * attempt, 10))
    raise RuntimeError(f"Failed to fetch page after {retries + 1} attempts: {last_error}")


def fetch_rows(
    country: str,
    timeout: float,
    delay: float,
    limit_pages: int | None,
    retries: int,
    quiet: bool,
    on_date: date | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    seen_pages = 0
    next_params: dict[str, str] | None = None
    overall_count: int | None = None
    seen_page_keys: set[tuple[tuple[str, str], ...]] = set()
    scanned_rows = 0
    base_params: dict[str, str] = {}
    query = ""
    if on_date is not None:
        query = join_caml(query, caml_state_on(on_date))
    if query:
        base_params["query"] = query

    with requests.Session() as session:
        while True:
            page_key = tuple(sorted((next_params or {}).items()))
            if page_key in seen_page_keys:
                raise RuntimeError(f"Pagination loop detected at params: {dict(page_key)}")
            seen_page_keys.add(page_key)

            request_params = {**base_params, **(next_params or {})}
            page = fetch_page(session, request_params, timeout=timeout, retries=retries)
            seen_pages += 1
            if page.overall_count is not None:
                overall_count = page.overall_count
            scanned_rows += len(page.rows)

            for row in page.rows:
                if row.get("country") == country:
                    matched.append({field: row.get(field) for field in OUTPUT_FIELDS})

            if not quiet:
                print(
                    json.dumps(
                        {
                            "page": seen_pages,
                            "page_rows": len(page.rows),
                            "scanned_rows": scanned_rows,
                            "matched": len(matched),
                            "next": bool(page.next_params),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

            if (
                not page.next_params
                or (overall_count is not None and scanned_rows >= overall_count)
                or (limit_pages is not None and seen_pages >= limit_pages)
            ):
                break
            next_params = page.next_params
            if delay > 0:
                time.sleep(delay)

    stats = {
        "country": country,
        "matched": len(matched),
        "pages": seen_pages,
        "scanned_rows": scanned_rows,
        "registry_total": overall_count,
        "on_date": on_date.isoformat() if on_date else None,
    }
    return matched, stats


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch EAEU SEZ residents filtered by country")
    parser.add_argument("--country", default="Беларусь")
    parser.add_argument("--output", type=Path, default=Path("data/eaeu/sez_residents_belarus.json"))
    parser.add_argument("--csv", type=Path, default=None, help="Optional CSV output path")
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--on-date", type=date.fromisoformat, default=None)
    parser.add_argument("--include-history", action="store_true", help="Do not apply portal state-on-date CAML filter")
    parser.add_argument("--limit-pages", type=int, default=None, help="Debug: stop after N pages")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows, stats = fetch_rows(
        country=args.country,
        timeout=args.timeout,
        delay=args.delay,
        limit_pages=args.limit_pages,
        retries=args.retries,
        quiet=args.quiet,
        on_date=None if args.include_history else args.on_date,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    stats["output"] = str(args.output)

    if args.csv:
        write_csv(args.csv, rows)
        stats["csv"] = str(args.csv)

    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
