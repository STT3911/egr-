"""Import scheduled inspection plan Excel files into PostgreSQL.

Usage:
  python scripts/imports/import_inspection_plan.py "C:\\Users\\User\\Downloads\\план проверок" --dry-run
  python scripts/imports/import_inspection_plan.py "C:\\Users\\User\\Downloads\\план проверок"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.services.inspection_plans import import_inspection_plan_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import scheduled inspection plan Excel files.")
    parser.add_argument("path", type=Path, help="Path to an .xlsx file or a directory with .xlsx files.")
    parser.add_argument("--batch-size", type=int, default=500, help="Rows per database upsert batch.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and match companies without writing to DB.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.path.exists():
        raise FileNotFoundError(args.path)
    if args.batch_size < 1:
        parser.error("--batch-size must be greater than zero")

    db = SessionLocal()
    try:
        stats = import_inspection_plan_path(
            db,
            args.path,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
    finally:
        db.close()
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
