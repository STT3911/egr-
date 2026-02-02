#!/usr/bin/env python3
"""
Неинтерактивный запуск обогащения и парсинга (для Docker / cron).

Использование:
  python scripts/run-enrich-and-parse.py
  python scripts/run-enrich-and-parse.py --limit 10000
  python scripts/run-enrich-and-parse.py --limit 50000 --rounds 5   # до 5 проходов по 50k
"""
import sys
import os
import argparse

# Корень приложения (в Docker — /app)
if os.path.exists("/app"):
    sys.path.insert(0, "/app")
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.logger import get_logger
from app.tasks.sync_tasks import enrich_missing_raw, process_pending_raw

logger = get_logger("enrich_parse")


def main():
    parser = argparse.ArgumentParser(description="Run enrichment + parsing (non-interactive)")
    parser.add_argument("--limit", type=int, default=50_000,
                        help="Max records per enrich/parse run (default: 50000)")
    parser.add_argument("--rounds", type=int, default=1,
                        help="Number of rounds (default: 1, use more to process all pending)")
    args = parser.parse_args()

    logger.info("🚀 Enrich + Parse (limit=%s, rounds=%s)", args.limit, args.rounds)

    for r in range(args.rounds):
        logger.info("--- Round %s/%s ---", r + 1, args.rounds)
        enriched = enrich_missing_raw(limit=args.limit)
        processed = process_pending_raw(limit=args.limit)
        logger.info("Round %s: enriched=%s, processed=%s", r + 1, enriched, processed)
        if enriched == 0 and processed == 0:
            logger.info("Nothing left to do.")
            break

    logger.info("🎉 Done.")


if __name__ == "__main__":
    main()
