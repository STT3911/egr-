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
    # Делегируем скрипту с теми же аргументами (без --to-db / --import-only)
    from scripts.run_nalog_debt import parse_args, run_fetcher

    args = parse_args()
    if args.import_only or args.to_db:
        # Если пользователь хочет БД — запускаем полный скрипт
        from scripts.run_nalog_debt import main as cli_main
        sys.exit(cli_main())
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
