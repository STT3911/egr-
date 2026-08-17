"""Export phones and emails for GIAS-accredited companies into separate CSV files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.services.company_contacts import rebuild_company_contacts
from app.services.gias_contact_export import export_gias_accredited_contacts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/gias_contacts"),
        help="Directory for the two CSV files (default: /tmp/gias_contacts)",
    )
    parser.add_argument(
        "--delimiter",
        default=";",
        help="One-character CSV delimiter (default: semicolon)",
    )
    parser.add_argument(
        "--rebuild-contacts",
        action="store_true",
        help="Refresh the all-source company_contacts aggregate before exporting",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db = SessionLocal()
    try:
        rebuild_result = None
        if args.rebuild_contacts:
            rebuild_result = rebuild_company_contacts(db)
        result = export_gias_accredited_contacts(
            db,
            args.output_dir,
            delimiter=args.delimiter,
        )
        if rebuild_result is not None:
            result["contacts_rebuild"] = rebuild_result
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
