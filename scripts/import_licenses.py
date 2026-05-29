"""Import a license.gov.by JSON snapshot into the database."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import license.gov.by JSON snapshot into DB")
    parser.add_argument("snapshot_json", type=Path, nargs="?", default=Path("data/licenses/licenses.json"))
    parser.add_argument("--batch-size", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    from app.core.database import SessionLocal
    from app.services.licenses import import_license_snapshot_json

    db = SessionLocal()
    try:
        stats = import_license_snapshot_json(db, args.snapshot_json, batch_size=args.batch_size)
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
