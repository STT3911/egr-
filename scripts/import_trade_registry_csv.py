"""Import Belarus trade registry CSV rows for UNPs already present in EGR DB.

Usage:
  python scripts/import_trade_registry_csv.py "C:\\path\\to\\trade_registry.csv" --dry-run
  python scripts/import_trade_registry_csv.py "C:\\path\\to\\trade_registry.csv"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.trade_registry_import import build_cli_parser, import_csv, infer_source_date


def main() -> None:
    parser = build_cli_parser()
    args = parser.parse_args()

    if not args.csv_path.exists():
        raise FileNotFoundError(args.csv_path)
    if args.batch_size < 1:
        parser.error("--batch-size must be greater than zero")

    source_date = args.source_date or infer_source_date(args.csv_path)
    stats = import_csv(
        args.csv_path,
        args.batch_size,
        args.dry_run,
        source_date,
        args.encoding,
        args.missing_output,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
