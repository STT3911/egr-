#!/usr/bin/env python3
"""Пересборка справочника gov_organizations из ЕГР + ГРП.

Запуск (в контейнере, где есть psycopg2):
  docker compose exec egr-api python /app/scripts/rebuild_gov_organizations.py
  docker compose exec egr-api python /app/scripts/rebuild_gov_organizations.py --joint-stock
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app.core.database import SessionLocal
from app.services.gov_organizations import rebuild


def print_breakdown():
    db = SessionLocal()
    try:
        print("\nПо категориям/принадлежности:")
        rows = db.execute(text(
            "SELECT category, ownership, count(*) FROM gov_organizations "
            "GROUP BY 1,2 ORDER BY 1,2"
        ))
        for cat, own, cnt in rows:
            print(f"  {cat:20s} {own:10s} {cnt}")
        total = db.execute(text("SELECT count(*) FROM gov_organizations")).scalar()
        print(f"  ИТОГО: {total}")
        print("\nПримеры (по 3 на категорию):")
        rows = db.execute(text(
            "SELECT DISTINCT ON (category) category, unp, full_name "
            "FROM gov_organizations ORDER BY category, unp"
        ))
        for cat, unp, name in rows:
            print(f"  [{cat}] {unp}  {name}")
    finally:
        db.close()


def main():
    p = argparse.ArgumentParser(description="Пересборка справочника госорганизаций")
    p.add_argument("--joint-stock", action="store_true",
                   help="включать все ОАО/ЗАО (ownership=unknown); по умолчанию только с гос-намёком")
    p.add_argument("--flush-every", type=int, default=1000)
    args = p.parse_args()

    print("=" * 70)
    print("  ПЕРЕСБОРКА СПРАВОЧНИКА ГОСОРГАНИЗАЦИЙ (egr_raw + grp_taxpayer)")
    print("=" * 70)
    stats = rebuild(include_joint_stock=args.joint_stock, flush_every=args.flush_every)
    print("\nГотово:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print_breakdown()


if __name__ == "__main__":
    main()
