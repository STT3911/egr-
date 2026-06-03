#!/usr/bin/env python3
"""
Unified management CLI for EGR/GRP parsers.

Usage:
  python manage.py status
  python manage.py egr fetch --days 7
  python manage.py egr fetch --start 01.01.2024 --end 31.12.2024
  python manage.py egr fetch --days 30 --json-only
  python manage.py egr enrich --limit 50000
  python manage.py egr enrich --limit 50000 --rounds 5
  python manage.py grp fetch --limit 10000
  python manage.py grp fetch --limit 10000 --all
"""
import argparse
import os
import sys
from datetime import date, timedelta

if os.path.exists("/app"):
    sys.path.insert(0, "/app")
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.logger import get_logger

logger = get_logger("manage")


def cmd_status(_args):
    from app.core.database import SessionLocal
    from app.database.models import RawCompanyData, Company, GrpTaxpayerData, GrpRawData
    from sqlalchemy import func, or_

    db = SessionLocal()
    try:
        total_raw = db.query(func.count(RawCompanyData.unp)).scalar() or 0
        needs_enrich = db.query(func.count(RawCompanyData.unp)).filter(
            or_(
                ~RawCompanyData.data.has_key("names"),
                ~RawCompanyData.data.has_key("addresses"),
                ~RawCompanyData.data.has_key("ved"),
            )
        ).scalar() or 0
        processed = db.query(func.count(RawCompanyData.unp)).filter(
            RawCompanyData.processed_at.isnot(None)
        ).scalar() or 0
        errors = db.query(func.count(RawCompanyData.unp)).filter(
            RawCompanyData.last_error.isnot(None)
        ).scalar() or 0
        total_companies = db.query(func.count(Company.id)).scalar() or 0

        grp_raw_total = db.query(func.count(GrpRawData.unp)).scalar() or 0
        grp_raw_unparsed = db.query(func.count(GrpRawData.unp)).filter(
            GrpRawData.parsed == False  # noqa: E712
        ).scalar() or 0
        grp_parsed = db.query(func.count(GrpTaxpayerData.unp)).scalar() or 0

        print("=" * 60)
        print("EGR STATUS")
        print(f"  Raw records:      {total_raw:>10,}")
        print(f"  Needs enrichment: {needs_enrich:>10,}")
        print(f"  Processed:        {processed:>10,}")
        print(f"  Errors:           {errors:>10,}")
        print(f"  Companies:        {total_companies:>10,}")
        print()
        print("GRP STATUS")
        print(f"  Raw records:      {grp_raw_total:>10,}")
        print(f"  Unparsed:         {grp_raw_unparsed:>10,}")
        print(f"  Parsed:           {grp_parsed:>10,}")
        print("=" * 60)
    finally:
        db.close()


def cmd_egr_fetch(args):
    from app.tasks.sync_tasks import fetch_period_to_json, auto_fetch_and_load

    if args.days is not None:
        end_date = date.today()
        start_date = end_date - timedelta(days=args.days)
    else:
        if not args.end:
            print("ERROR: --start requires --end", file=sys.stderr)
            sys.exit(1)
        try:
            d, m, y = args.start.split('.')
            start_date = date(int(y), int(m), int(d))
            d, m, y = args.end.split('.')
            end_date = date(int(y), int(m), int(d))
        except Exception:
            print("ERROR: dates must be in DD.MM.YYYY format", file=sys.stderr)
            sys.exit(1)

    start_str = start_date.strftime("%d.%m.%Y")
    end_str = end_date.strftime("%d.%m.%Y")

    logger.info("EGR fetch: %s — %s", start_str, end_str)

    if args.json_only:
        count = fetch_period_to_json(start_str, end_str)
        logger.info("Fetched %s companies → JSON", count)
    else:
        count = auto_fetch_and_load(start_str, end_str)
        logger.info("Fetched and loaded %s companies", count)


def cmd_egr_enrich(args):
    from app.tasks.sync_tasks import enrich_missing_raw, process_pending_raw

    for round_num in range(1, args.rounds + 1):
        if args.rounds > 1:
            logger.info("Round %s/%s", round_num, args.rounds)
        enriched = enrich_missing_raw(limit=args.limit)
        processed = process_pending_raw(limit=args.limit)
        logger.info("enriched=%s  processed=%s", enriched, processed)
        if enriched == 0 and processed == 0:
            logger.info("Nothing left to do")
            break


def cmd_grp_fetch(args):
    from app.tasks.sync_tasks import fetch_grp_to_json, auto_fetch_grp_and_load

    only_missing = not args.all

    logger.info(
        "GRP fetch: limit=%s  only_missing=%s  json_only=%s",
        args.limit, only_missing, args.json_only,
    )

    if args.json_only:
        count = fetch_grp_to_json(limit=args.limit, only_missing=only_missing)
        logger.info("Fetched %s taxpayers → JSON", count)
    else:
        count = auto_fetch_grp_and_load(limit=args.limit, only_missing=only_missing)
        logger.info("Fetched and loaded %s taxpayers", count)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manage.py",
        description="EGR/GRP management CLI",
    )
    subs = parser.add_subparsers(dest="command", required=True)

    # ── status ────────────────────────────────────────────────────────────────
    subs.add_parser("status", help="Show data status")

    # ── egr ───────────────────────────────────────────────────────────────────
    egr = subs.add_parser("egr", help="EGR operations")
    egr_subs = egr.add_subparsers(dest="subcommand", required=True)

    egr_fetch = egr_subs.add_parser("fetch", help="Fetch EGR data from API")
    period_group = egr_fetch.add_mutually_exclusive_group(required=True)
    period_group.add_argument("--days", type=int, metavar="N", help="Last N days")
    period_group.add_argument("--start", metavar="DD.MM.YYYY", help="Start date (use with --end)")
    egr_fetch.add_argument("--end", metavar="DD.MM.YYYY", help="End date")
    egr_fetch.add_argument(
        "--json-only", action="store_true",
        help="Save to JSON only, skip immediate DB load",
    )

    egr_enrich = egr_subs.add_parser("enrich", help="Enrich and process pending EGR data")
    egr_enrich.add_argument("--limit", type=int, default=50_000, metavar="N")
    egr_enrich.add_argument("--rounds", type=int, default=1, metavar="N",
                             help="Repeat up to N times until queue is empty")

    # ── grp ───────────────────────────────────────────────────────────────────
    grp = subs.add_parser("grp", help="GRP (tax) operations")
    grp_subs = grp.add_subparsers(dest="subcommand", required=True)

    grp_fetch = grp_subs.add_parser("fetch", help="Fetch GRP taxpayer data from API")
    grp_fetch.add_argument("--limit", type=int, default=10_000, metavar="N")
    grp_fetch.add_argument("--all", action="store_true",
                            help="Include UNPs that already have GRP data (re-fetch)")
    grp_fetch.add_argument(
        "--json-only", action="store_true",
        help="Save to JSON only, skip immediate DB load",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "status":
        cmd_status(args)
    elif args.command == "egr":
        if args.subcommand == "fetch":
            cmd_egr_fetch(args)
        elif args.subcommand == "enrich":
            cmd_egr_enrich(args)
    elif args.command == "grp":
        if args.subcommand == "fetch":
            cmd_grp_fetch(args)


if __name__ == "__main__":
    main()
