#!/usr/bin/env python3
"""
CLI for fetching tax debt data from portal.nalog.gov.by and optionally importing it into DB.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.nalog_debt import run_fetcher, run_import_to_db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch tax debt data and optionally import it into the database",
    )
    parser.add_argument("--start", default="2017-01-01", help="YYYY-MM-DD")
    parser.add_argument("--end", default="2026-01-01", help="YYYY-MM-DD")
    parser.add_argument(
        "--out",
        default=None,
        help="Output directory for JSON files. Defaults to NALOG_DEBT_OUT_DIR.",
    )
    parser.add_argument(
        "--perm",
        default="",
        help="X-GWT-Permutation. If omitted, it is resolved automatically.",
    )
    parser.add_argument("--jsessionid", default="", help="JSESSIONID from browser")
    parser.add_argument(
        "--cookie-header",
        default="",
        help="Full Cookie header from browser",
    )
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip dates that already have output files",
    )
    parser.add_argument("--sleep-min", type=float, default=0.10)
    parser.add_argument("--sleep-max", type=float, default=0.30)
    parser.add_argument(
        "--mode",
        default="range",
        choices=["range", "monthly"],
        help="range: full date range; monthly: current month only",
    )
    parser.add_argument(
        "--to-db",
        action="store_true",
        help="Import fetched JSON files into nalog_debt_records after download",
    )
    parser.add_argument(
        "--import-only",
        action="store_true",
        help="Only import JSON files from --out into DB without portal requests",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out or settings.NALOG_DEBT_OUT_DIR)

    if args.import_only:
        db = SessionLocal()
        try:
            total = run_import_to_db(out_dir, db)
            print(f"Import completed: {total} records")
        finally:
            db.close()
        return 0

    run_fetcher(
        start_date=args.start,
        end_date=args.end,
        out_dir=out_dir,
        perm=args.perm or None,
        jsessionid=args.jsessionid.strip() or None,
        cookie_header=args.cookie_header.strip() or None,
        timeout=args.timeout,
        retries=args.retries,
        workers=args.workers,
        overwrite=args.overwrite,
        skip_existing=args.skip_existing,
        sleep_min=args.sleep_min,
        sleep_max=args.sleep_max,
        mode=args.mode,
    )

    if args.to_db:
        db = SessionLocal()
        try:
            total = run_import_to_db(out_dir, db)
            print(f"DB import completed: {total} records")
        finally:
            db.close()

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
