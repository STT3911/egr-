"""CLI: fetch EAEU SEZ residents filtered by country and save to JSON/CSV.

Тонкая обёртка над app.services.eaeu_sez_fetch (логика обхода/парсинга — там).

Examples:
  python scripts/fetch_eaeu_sez_residents.py
  python scripts/fetch_eaeu_sez_residents.py --output data/eaeu/sez_belarus.json --csv data/eaeu/sez_belarus.csv
  python scripts/fetch_eaeu_sez_residents.py --country Беларусь --limit-pages 2
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.eaeu_sez_fetch import OUTPUT_FIELDS, fetch_rows


def write_csv(path: Path, rows: list[dict]) -> None:
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
