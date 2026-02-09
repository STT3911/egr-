#!/usr/bin/env python3
"""
CLI: сбор данных о задолженности с portal.nalog.gov.by и опционально импорт в БД.
Использование:
  python scripts/run_nalog_debt.py --start 2020-01-01 --end 2025-12-01 --skip-existing
  python scripts/run_nalog_debt.py --to-db --out dolg_data
  python scripts/run_nalog_debt.py --import-only --out dolg_data
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Добавить корень проекта в path
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.nalog_debt import run_fetcher, run_import_to_db


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Сбор данных о задолженности (portal.nalog.gov.by) и импорт в БД"
    )
    p.add_argument("--start", default="2017-01-01", help="YYYY-MM-DD")
    p.add_argument("--end", default="2026-01-01", help="YYYY-MM-DD")
    p.add_argument("--out", default=None, help="Папка для JSON (по умолчанию из NALOG_DEBT_OUT_DIR)")
    p.add_argument("--perm", default="", help="X-GWT-Permutation (если пусто — подставляется автоматически)")
    p.add_argument("--jsessionid", default="", help="JSESSIONID из браузера")
    p.add_argument("--timeout", type=float, default=45.0)
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--skip-existing", action="store_true", help="Пропускать уже существующие файлы дат")
    p.add_argument("--sleep-min", type=float, default=0.10)
    p.add_argument("--sleep-max", type=float, default=0.30)
    p.add_argument(
        "--mode",
        default="range",
        choices=["range", "monthly"],
        help="range: весь диапазон; monthly: только текущий месяц",
    )
    p.add_argument(
        "--to-db",
        action="store_true",
        help="После сбора импортировать JSON в таблицу nalog_debt_records",
    )
    p.add_argument(
        "--import-only",
        action="store_true",
        help="Только импорт из папки --out в БД (без запросов к порталу)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out or settings.NALOG_DEBT_OUT_DIR)

    if args.import_only:
        db = SessionLocal()
        try:
            total = run_import_to_db(out_dir, db)
            print(f"Импорт завершён: {total} записей")
        finally:
            db.close()
        return 0

    run_fetcher(
        start_date=args.start,
        end_date=args.end,
        out_dir=out_dir,
        perm=args.perm or None,
        jsessionid=args.jsessionid.strip() or None,
        timeout=args.timeout,
        retries=args.retries,
        workers=args.workers,
        overwrite=args.overwrite,
        skip_existing=args.skip_existing,
        sleep_min=args.sleep_min,
        sleep_max=args.sleep_max,
        mode=args.mode,
    )

    if args.to_db:
        db = SessionLocal()
        try:
            total = run_import_to_db(out_dir, db)
            print(f"Импорт в БД завершён: {total} записей")
        finally:
            db.close()

    print("Готово.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
