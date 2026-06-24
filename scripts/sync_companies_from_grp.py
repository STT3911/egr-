#!/usr/bin/env python3
"""Занос УНП из ГРП в центральный реестр egr_companies.

Часть конвейера добора госорганов:
  unp_enumerate.py → grp_raw_data → grp_process_raw → grp_taxpayer_data
  → sync_companies_from_grp (этот скрипт) → rebuild_gov_organizations.py

Запуск:
  docker exec egr_api python /app/scripts/sync_companies_from_grp.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app.core.database import SessionLocal
from app.services.company_registry import sync_companies_from_grp


def main():
    print("=" * 70)
    print("  ЗАНОС УНП ИЗ ГРП В ЦЕНТРАЛЬНЫЙ РЕЕСТР egr_companies")
    print("=" * 70)
    stats = sync_companies_from_grp()
    print("\nГотово:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT source, count(*) FROM egr_companies GROUP BY 1 ORDER BY 1"
        ))
        print("\negr_companies по источнику:")
        for src, cnt in rows:
            print(f"  {src}: {cnt}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
