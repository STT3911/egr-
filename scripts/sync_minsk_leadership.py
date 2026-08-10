"""Fetch and import public leadership observations from komtrud.minsk.gov.by."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.minsk_leadership import sync_minsk_leadership


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import dated Minsk occupational-safety leadership observations"
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch and match without writing")
    parser.add_argument("--timeout", type=float, default=settings.MINSK_LEADERSHIP_TIMEOUT_SECONDS)
    parser.add_argument("--retries", type=int, default=settings.MINSK_LEADERSHIP_RETRIES)
    parser.add_argument(
        "--delay",
        type=float,
        default=settings.MINSK_LEADERSHIP_REQUEST_DELAY_SECONDS,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db = SessionLocal()
    try:
        result = sync_minsk_leadership(
            db,
            timeout=args.timeout,
            retries=args.retries,
            delay=args.delay,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result["status"] in {"ok", "partial"} else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
