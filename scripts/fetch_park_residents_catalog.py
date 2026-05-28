"""Fetch the park.by residents catalog to a JSON snapshot.

Examples:
  python scripts/fetch_park_residents_catalog.py --output data/pvt/park_residents.json
  python scripts/fetch_park_residents_catalog.py --prefixes АБ12 --limit 20 --output /tmp/pvt_sample.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch park.by residents catalog to JSON")
    parser.add_argument("--output", type=Path, default=Path("data/pvt/park_residents.json"))
    parser.add_argument("--prefixes", default=None, help="Catalog prefixes to fetch, e.g. АБВ123. Defaults to Russian letters plus 1-9")
    parser.add_argument("--letters", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--proxy", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    from app.services.park_residents import fetch_catalog_snapshot

    prefixes = args.prefixes or args.letters
    letters = list(prefixes) if prefixes else None
    rows = fetch_catalog_snapshot(
        output=args.output,
        letters=letters,
        delay=args.delay,
        timeout=args.timeout,
        proxy=args.proxy,
        limit=args.limit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps([asdict(row) for row in rows], ensure_ascii=False, indent=2), encoding="utf-8")
    stats = {
        "total": len(rows),
        "found": sum(1 for row in rows if row.status == "found"),
        "invalid": sum(1 for row in rows if row.status == "invalid"),
        "output": str(args.output),
    }
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
