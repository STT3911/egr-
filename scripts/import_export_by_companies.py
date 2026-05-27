"""Import export.by company JSON and link rows to EGR companies by resolved UNP.

Example:
    python scripts/import_export_by_companies.py data/expo/export_by_companies_BY_2026-05-27.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import export.by company records into PostgreSQL")
    parser.add_argument("json_path", type=Path, help="Path to export.by JSON array")
    parser.add_argument("--batch-size", type=int, default=500, help="Commit every N saved rows")
    parser.add_argument("--dry-run", action="store_true", help="Only calculate match stats, do not write rows")
    parser.add_argument("--fuzzy", action="store_true", help="Enable slow trigram fallback for unresolved exact matches")
    parser.add_argument("--no-fuzzy", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--limit", type=int, default=None, help="Process only first N accepted rows")
    parser.add_argument(
        "--country",
        default="Беларусь",
        help="Import only rows with this country value; pass empty string with --all-countries to disable",
    )
    parser.add_argument("--all-countries", action="store_true", help="Disable country filtering")
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("data/expo/export_by_import_report.json"),
        help="Where to write ambiguous/not_found rows with candidates",
    )
    parser.add_argument("--no-report", action="store_true", help="Do not write an import report")
    parser.add_argument("--progress-every", type=int, default=500, help="Print progress every N processed rows")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    from app.core.database import SessionLocal
    from app.services.export_by_import import import_export_by_json

    def print_progress(processed: int, stats: dict[str, int]) -> None:
        print(
            "processed={processed} matched={matched} ambiguous={ambiguous} not_found={not_found}".format(
                processed=processed,
                matched=stats.get("matched", 0),
                ambiguous=stats.get("ambiguous", 0),
                not_found=stats.get("not_found", 0),
            ),
            flush=True,
        )

    db = SessionLocal()
    try:
        stats = import_export_by_json(
            db,
            args.json_path,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            use_fuzzy=args.fuzzy and not args.no_fuzzy,
            country=None if args.all_countries else args.country,
            report_path=None if args.no_report else args.report_path,
            progress=print_progress,
            progress_every=args.progress_every,
            limit=args.limit,
        )
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
