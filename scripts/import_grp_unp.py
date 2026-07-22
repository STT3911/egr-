#!/usr/bin/env python3
"""Import one or more missing UNPs from GRP into the central company registry."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.services.grp_discovery import discover_company_from_grp


async def run(unps: list[int]) -> int:
    db = SessionLocal()
    imported = 0
    try:
        for unp in unps:
            ok = await discover_company_from_grp(db, unp)
            print(f"{unp}: {'imported' if ok else 'not found'}")
            imported += int(ok)
    finally:
        db.close()
    return imported


def main() -> None:
    parser = argparse.ArgumentParser(description="Import missing companies from GRP by UNP")
    parser.add_argument("unp", nargs="+", type=int, help="One or more 9-digit UNPs")
    args = parser.parse_args()
    imported = asyncio.run(run(args.unp))
    raise SystemExit(0 if imported == len(args.unp) else 1)


if __name__ == "__main__":
    main()
