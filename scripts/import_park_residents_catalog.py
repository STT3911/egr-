"""Import a park.by residents JSON snapshot into pvt_resident_records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import park.by residents JSON snapshot into DB")
    parser.add_argument("snapshot_json", type=Path)
    parser.add_argument("--batch-size", type=int, default=500)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    from app.core.database import SessionLocal
    from app.services.park_residents import import_pvt_snapshot_json

    db = SessionLocal()
    try:
        stats = import_pvt_snapshot_json(db, args.snapshot_json, batch_size=args.batch_size)
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
