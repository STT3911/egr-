#!/usr/bin/env python3
"""Полная досборка госорганов: process → sync → rebuild (одной командой).

Шаги:
  1. grp_process_raw — парсит grp_raw_data (parsed=false) в grp_taxpayer_data
     (то, что нашёл перебор unp_enumerate.py), циклом до конца.
  2. sync_companies_from_grp — заносит новые УНП в центральный реестр egr_companies
     (source='grp') + имя в историю.
  3. rebuild_gov_organizations — пересобирает справочник и проставляет company_id.

Идемпотентно — можно запускать сколько угодно раз (в т.ч. пока перебор ещё идёт).

Запуск:
  docker exec egr_api python /app/scripts/gov_pipeline.py
  docker exec egr_api python /app/scripts/gov_pipeline.py --joint-stock
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.logger import get_logger
from app.services.company_registry import sync_companies_from_grp
from app.services.gov_organizations import rebuild

logger = get_logger("gov_pipeline")


def process_all_grp_raw(batch: int = 2000) -> int:
    """Парсит весь grp_raw_data (parsed=false) циклом, возвращает сколько распарсено."""
    from app.tasks.sync_tasks import grp_process_raw
    total = 0
    while True:
        n = grp_process_raw(limit=batch)
        if not n:
            break
        total += n
        print(f"  ...распарсено {total}")
    return total


def main():
    p = argparse.ArgumentParser(description="Досборка справочника госорганов")
    p.add_argument("--joint-stock", action="store_true", help="включать все ОАО/ЗАО")
    p.add_argument("--batch", type=int, default=2000, help="размер пачки парсинга ГРП")
    p.add_argument("--skip-process", action="store_true", help="пропустить шаг парсинга grp_raw")
    args = p.parse_args()

    print("=" * 70)
    print("  ДОСБОРКА ГОСОРГАНОВ: process → sync → rebuild")
    print("=" * 70)

    if not args.skip_process:
        print("\n[1/3] Парсинг grp_raw_data → grp_taxpayer_data ...")
        parsed = process_all_grp_raw(args.batch)
        print(f"  Распарсено всего: {parsed}")
    else:
        print("\n[1/3] Парсинг пропущен (--skip-process)")

    print("\n[2/3] Занос УНП в центральный реестр egr_companies ...")
    s = sync_companies_from_grp()
    print(f"  Компаний добавлено: {s['companies_added']}, имён: {s['names_added']}")

    print("\n[3/3] Пересборка справочника gov_organizations ...")
    stats = rebuild(include_joint_stock=args.joint_stock)
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print("\nГотово.")


if __name__ == "__main__":
    main()
