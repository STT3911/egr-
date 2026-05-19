"""Parse Belarus Hi-Tech Park residents by UNP.

Examples:
  python scripts/parse_park_residents.py --unp 193360017 --output data/imports/reports/pvt_residents.csv
  python scripts/parse_park_residents.py --input trade_registry_missing_unps.csv --output pvt_residents.csv
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.park_residents import (
    ParkResidentResult,
    clean_unp,
    fetch_resident,
    iter_unps_from_csv,
    write_results,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse park.by residents by UNP.")
    parser.add_argument("--unp", action="append", default=[], help="UNP to check; can be passed multiple times")
    parser.add_argument("--input", type=Path, default=None, help="CSV file with UNP values")
    parser.add_argument("--output", type=Path, required=True, help="Output .csv or .json")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay", type=float, default=0.3, help="Delay between requests, seconds")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--proxy", default=None, help="Optional proxy URL, e.g. http://127.0.0.1:10809")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    unps = [unp for unp in (clean_unp(value) for value in args.unp) if unp]
    if args.input:
        unps.extend(iter_unps_from_csv(args.input, args.limit))

    unique_unps = []
    seen = set()
    for unp in unps:
        if unp in seen:
            continue
        seen.add(unp)
        unique_unps.append(unp)
        if args.limit and len(unique_unps) >= args.limit:
            break

    if not unique_unps:
        raise SystemExit("No valid UNP values were provided")

    results: list[ParkResidentResult] = []
    for index, unp in enumerate(unique_unps, start=1):
        try:
            parsed = fetch_resident(unp, timeout=args.timeout, proxy=args.proxy)
            results.append(parsed)
            print(f"[{index}/{len(unique_unps)}] {unp}: {parsed.status} {parsed.name or ''}", flush=True)
        except Exception as exc:
            results.append(ParkResidentResult(unp=unp, status="error", error=repr(exc)))
            print(f"[{index}/{len(unique_unps)}] {unp}: error {exc}", flush=True)
        if args.delay > 0 and index < len(unique_unps):
            time.sleep(args.delay)

    write_results(args.output, results)
    stats = {
        "total": len(results),
        "found": sum(1 for row in results if row.status == "found"),
        "not_found": sum(1 for row in results if row.status == "not_found"),
        "errors": sum(1 for row in results if row.status == "error"),
        "output": str(args.output),
        "items": [asdict(row) for row in results[:5]],
    }
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
