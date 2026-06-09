"""Fetch license.gov.by records to a JSON snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch license.gov.by records to JSON")
    parser.add_argument("--output", type=Path, default=Path("data/licenses/licenses.json"))
    parser.add_argument("--page-size", type=int, default=None)
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--delay", type=float, default=None)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=2.0)
    parser.add_argument("--no-verify-tls", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    from app.services.licenses import fetch_license_snapshot

    stats = fetch_license_snapshot(
        args.output,
        page_size=args.page_size,
        start_page=args.start_page,
        max_pages=args.max_pages,
        delay=args.delay,
        timeout=args.timeout,
        retries=args.retries,
        retry_delay=args.retry_delay,
        verify_tls=False if args.no_verify_tls else None,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
