"""Fetch/import BelTPP own-production certificates from cci.by.

Usage:
  python scripts/imports/import_belltpp_own_certificates.py fetch --output data/imports/belltpp_own_certificates/snapshot.json
  python scripts/imports/import_belltpp_own_certificates.py import data/imports/belltpp_own_certificates/snapshot.json
  python scripts/imports/import_belltpp_own_certificates.py sync --output data/imports/belltpp_own_certificates/snapshot.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.belltpp_own_certificates import fetch_and_import, fetch_snapshot, import_snapshot


def default_snapshot_path() -> Path:
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return Path("data/imports/belltpp_own_certificates") / f"belltpp_own_certificates_{stamp}.json"


def add_fetch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--page-size", type=int, default=20, help="Source page size.")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit pages for testing.")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between source requests in seconds.")


def add_import_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--batch-size", type=int, default=500, help="Rows per database upsert batch.")
    parser.add_argument("--dry-run", action="store_true", help="Parse/match without writing to DB.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch/import BelTPP own-production certificates.")
    subparsers = parser.add_subparsers(dest="command")

    fetch_parser = subparsers.add_parser("fetch", help="Fetch cci.by registry into JSON snapshot.")
    add_fetch_args(fetch_parser)
    fetch_parser.add_argument("--output", type=Path, default=None, help="Snapshot JSON path.")

    import_parser = subparsers.add_parser("import", help="Import a JSON snapshot into DB.")
    import_parser.add_argument("input", type=Path, help="Snapshot JSON path.")
    add_import_args(import_parser)

    sync_parser = subparsers.add_parser("sync", help="Fetch snapshot and import it into DB.")
    add_fetch_args(sync_parser)
    add_import_args(sync_parser)
    sync_parser.add_argument("--output", type=Path, default=None, help="Snapshot JSON path.")

    return parser


def validate_common(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if getattr(args, "page_size", 1) < 1:
        parser.error("--page-size must be greater than zero")
    if getattr(args, "batch_size", 1) < 1:
        parser.error("--batch-size must be greater than zero")
    if getattr(args, "max_pages", None) is not None and args.max_pages < 1:
        parser.error("--max-pages must be greater than zero")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        args.command = "sync"
        args.output = None
        args.page_size = 20
        args.max_pages = None
        args.delay = 0.2
        args.batch_size = 500
        args.dry_run = False

    validate_common(args, parser)

    if args.command == "fetch":
        output = args.output or default_snapshot_path()
        stats = fetch_snapshot(
            output,
            page_size=args.page_size,
            max_pages=args.max_pages,
            delay=args.delay,
        )
    elif args.command == "import":
        if not args.input.exists():
            raise FileNotFoundError(args.input)
        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            stats = import_snapshot(
                db,
                args.input,
                batch_size=args.batch_size,
                dry_run=args.dry_run,
            )
        finally:
            db.close()
    else:
        output = args.output or default_snapshot_path()
        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            stats = fetch_and_import(
                db,
                page_size=args.page_size,
                max_pages=args.max_pages,
                delay=args.delay,
                batch_size=args.batch_size,
                dry_run=args.dry_run,
                output=output,
            )
        finally:
            db.close()

    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
