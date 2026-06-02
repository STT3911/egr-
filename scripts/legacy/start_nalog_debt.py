#!/usr/bin/env python3
"""
Точка входа для сбора данных о задолженности с portal.nalog.gov.by.
Вся логика перенесена в app.services.nalog_debt; для импорта в БД используйте:
  python scripts/run_nalog_debt.py --to-db ...
"""
from __future__ import annotations

import sys
from pathlib import Path

# Корень проекта в path
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


def main() -> None:
    import argparse
    
    # Парсинг аргументов (без --to-db / --import-only для простоты)
    parser = argparse.ArgumentParser(description="Сбор данных о задолженности с portal.nalog.gov.by")
    parser.add_argument("--start", default="2017-01-01", help="YYYY-MM-DD")
    parser.add_argument("--end", default="2026-01-01", help="YYYY-MM-DD")
    parser.add_argument("--out", default=None, help="Папка для JSON")
    parser.add_argument("--perm", default="", help="X-GWT-Permutation")
    parser.add_argument("--jsessionid", default="", help="JSESSIONID")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--sleep-min", type=float, default=0.10)
    parser.add_argument("--sleep-max", type=float, default=0.30)
    parser.add_argument("--mode", default="range", choices=["range", "monthly"])
    parser.add_argument("--to-db", action="store_true", help="Импорт в БД (требует зависимости)")
    parser.add_argument("--import-only", action="store_true", help="Только импорт (требует зависимости)")
    
    args = parser.parse_args()
    
    # Если нужна БД — используем полный скрипт (требует зависимости)
    if args.import_only or args.to_db:
        try:
            from scripts.run_nalog_debt import main as cli_main
            sys.exit(cli_main())
        except ImportError as e:
            print(f"Ошибка: для импорта в БД нужны зависимости приложения: {e}")
            print("Установите: pip install -r requirements.txt")
            sys.exit(1)
    
    # Простой сбор в JSON (работает без зависимостей приложения)
    from app.services.nalog_debt import run_fetcher
    
    run_fetcher(
        start_date=args.start,
        end_date=args.end,
        out_dir=Path(args.out) if args.out else None,
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
    print("Готово.")


if __name__ == "__main__":
    main()
    sys.exit(0)
