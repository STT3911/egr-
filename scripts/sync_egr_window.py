"""Resume an isolated date window, or the existing main cursor with --backlog.

Uses the daily sync lock and the same strict fetch/import/event pipeline.
No task is enqueued. Each invocation is bounded and safe to resume.
"""
import argparse
import asyncio
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.services.aggregator import AggregatorService
from app.services.egr_client import EGRClient
from app.services.egr_period_sync import STATE_KEY, PeriodSyncStore, run_period_sync


def window_key(start, end):
    if start > end or end >= datetime.now(timezone(timedelta(hours=3))).date():
        raise ValueError("Use an ordered window of completed Minsk calendar days")
    return f"egr_period_window:{start.isoformat()}:{end.isoformat()}"


async def sync_window(start, end, expected_database, *, max_companies=500, max_seconds=1200, backlog=False):
    validated_key = window_key(start, end)
    key = STATE_KEY if backlog else validated_key
    # Keep this connection/transaction open: commits in the importer's
    # separate sessions must not release the shared daily-sync lock.
    with engine.begin() as lock:
        database = lock.execute(text("SELECT current_database()")).scalar_one()
        if database != expected_database:
            raise RuntimeError("Unexpected database; no synchronization performed")
        if not lock.execute(text("SELECT pg_try_advisory_xact_lock(hashtext(:name))"),
                            {"name": "egr:period_sync_v2"}).scalar():
            return {"status": "already_running", "checkpoint": key}
        db = SessionLocal()
        client = EGRClient(settings.EGR_API_URL)
        aggregator = AggregatorService()
        try:
            async def refresh(unp):
                payload = await client.get_full_company_history_strict(
                    unp, delay=settings.EGR_PERIOD_REQUEST_DELAY)
                raw = aggregator.save_raw_payload(unp, payload)
                aggregator.process_raw_data(unp, raw_entry=raw, authoritative_addresses=True)
                if aggregator.redis is not None:
                    aggregator.redis.delete(f"company_profile_v2:{unp}")

            store = PeriodSyncStore(db, state_key=key)
            state = store.load()
            if backlog and not state:
                raise ValueError("Backlog checkpoint missing; refusing implicit bootstrap")
            if state and not backlog and state.get("target") != end.isoformat():
                raise ValueError("Window checkpoint target mismatch")
            result = await run_period_sync(
                store, client, refresh, target=end,
                bootstrap_days=(end - start).days + 1, overlap_days=1,
                max_companies=max_companies, max_seconds=max_seconds,
                delay=settings.EGR_PERIOD_REQUEST_DELAY,
                row_limit=settings.EGR_PERIOD_ROW_LIMIT)
            return {**result, "checkpoint": key}
        finally:
            await client.close()
            await aggregator.egr_client.close()
            if aggregator.mobile_client:
                await aggregator.mobile_client.close()
            aggregator.close()
            db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-from", required=True, type=date.fromisoformat)
    parser.add_argument("--date-to", required=True, type=date.fromisoformat)
    parser.add_argument("--database", required=True, help="Expected PostgreSQL database name")
    parser.add_argument("--max-companies", type=int, default=500)
    parser.add_argument("--max-seconds", type=int, default=1200)
    parser.add_argument("--backlog", action="store_true", help="Resume existing main cursor; date-from does not reset it")
    parser.add_argument("--max-batches", type=int, default=1)
    parser.add_argument("--total-seconds", type=int, default=1200)
    args = parser.parse_args()
    if min(args.max_batches, args.total_seconds, args.max_seconds, args.max_companies) < 1:
        parser.error("Budgets must be positive")
    return asyncio.run(run_batches(args))


async def run_batches(args):
    started = time.monotonic()
    for _ in range(args.max_batches):
        remaining = args.total_seconds - (time.monotonic() - started)
        if remaining <= 0:
            break
        result = await sync_window(args.date_from, args.date_to, args.database,
                                  max_companies=args.max_companies,
                                  max_seconds=min(args.max_seconds, remaining), backlog=args.backlog)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if result["status"] == "blocked":
            return 3
        if result["status"] == "up_to_date" or (
            result["status"] == "complete" and result["target"] == args.date_to.isoformat()
        ):
            return 0
        await asyncio.sleep(min(30 if result["status"] == "already_running" else 5,
                                max(0, args.total_seconds - (time.monotonic() - started))))
    print(json.dumps({"status": "budget_exhausted", "resume": "Run the same command; progress is saved"}), flush=True)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
