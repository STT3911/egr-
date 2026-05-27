"""Fetch export.by company cards to a JSON file.

By default this downloads Belarus companies only, because export.by records do
not include UNP and the local EGR database can only link Belarus entities.

Example:
    python scripts/fetch_export_by_companies.py --output data/expo/export_by_companies_BY.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import requests


BASE_URL = "https://export.by/back/search/company"
PAGE_SIZE = 20


def page_fingerprint(rows: list[dict[str, Any]]) -> tuple[Any, ...]:
    return tuple(row.get("id") for row in rows)


def fetch_page(session: requests.Session, page: int, country_code: str | None, timeout: float) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"page": page}
    if country_code:
        params["country_code"] = country_code
    response = session.get(BASE_URL, params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected response for page {page}: expected JSON array")
    return payload


def find_last_page(session: requests.Session, country_code: str | None, timeout: float) -> int:
    hi = 1
    seen: dict[tuple[Any, ...], int] = {}
    beyond_fingerprint: tuple[Any, ...] | None = None

    while True:
        rows = fetch_page(session, hi, country_code, timeout)
        fingerprint = page_fingerprint(rows)
        if len(rows) < PAGE_SIZE:
            beyond_fingerprint = fingerprint
            break
        if fingerprint in seen:
            beyond_fingerprint = fingerprint
            break
        seen[fingerprint] = hi
        hi *= 2

    lo = 1
    while lo < hi:
        mid = (lo + hi) // 2
        rows = fetch_page(session, mid, country_code, timeout)
        if len(rows) < PAGE_SIZE or page_fingerprint(rows) == beyond_fingerprint:
            hi = mid
        else:
            lo = mid + 1
    return lo


def fetch_all(country_code: str | None, timeout: float, delay: float) -> list[dict[str, Any]]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    last_page = find_last_page(session, country_code, timeout)
    print(f"last_page={last_page}", flush=True)

    rows: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for page in range(1, last_page + 1):
        page_rows = fetch_page(session, page, country_code, timeout)
        for row in page_rows:
            row_id = row.get("id")
            if isinstance(row_id, int) and row_id in seen_ids:
                continue
            if isinstance(row_id, int):
                seen_ids.add(row_id)
            rows.append(row)
        if page % 50 == 0 or page == last_page:
            print(f"fetched page={page} records={len(rows)}", flush=True)
        if delay > 0 and page < last_page:
            time.sleep(delay)
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch export.by companies to JSON")
    parser.add_argument("--country-code", default="BY", help="export.by country_code filter; empty disables filtering")
    parser.add_argument("--output", type=Path, default=Path("data/expo/export_by_companies_BY.json"))
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--delay", type=float, default=0.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    country_code = args.country_code or None
    rows = fetch_all(country_code, args.timeout, args.delay)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"DONE file={args.output} records={len(rows)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
