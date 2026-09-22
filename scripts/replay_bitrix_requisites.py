"""Preview first; opt-in missing-only recovery for one verified Bitrix portal."""
import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.bitrix.database import AsyncSessionLocal, async_engine
from app.bitrix.egr_client import EGRClient
from app.bitrix.recovery import RecoveryClient, discover, recover, save_state
from app.bitrix.requisite_service import RequisiteService
from app.bitrix.security import portal_domain
from app.services.egr_contract import MINSK


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        result = MINSK.localize(result)
    return result.isoformat()


async def run(args):
    domain = portal_domain(args.domain)
    since = timestamp(args.since)
    path = Path(args.state_file)
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("version") != 1 or state["domain"] != domain or state["since"] != since:
            raise ValueError("Checkpoint belongs to another portal/period/version")
        if args.until and timestamp(args.until) != state["until"]:
            raise ValueError("Checkpoint end date cannot change")
    else:
        state = {"version": 1, "domain": domain, "since": since,
                 "until": timestamp(args.until) if args.until else datetime.now(MINSK).isoformat(),
                 "company_ids": [], "next_index": 0, "preview_index": 0,
                 "discovery": {key: {"last_id": 0, "complete": False} for key in ("DATE_CREATE", "DATE_MODIFY")}}
    if datetime.fromisoformat(state["since"]) > datetime.fromisoformat(state["until"]):
        raise ValueError("since must precede until")
    if args.apply and (not args.accept_portal_events or not state["company_ids"]
                       or state.get("preview_index", 0) != len(state["company_ids"])):
        raise ValueError("Complete preview first; --apply also requires --accept-portal-events")
    async with async_engine.begin() as connection:
        locked = (await connection.execute(text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"),
                  {"key": "bitrix:recovery:" + domain})).scalar()
        if not locked:
            raise RuntimeError("Another recovery is running for this portal")
        async with AsyncSessionLocal() as db:
            client = RecoveryClient(db, domain=domain, apply=args.apply)
            await client.verify_application()
            checkpoint = lambda value: save_state(path, value)
            await discover(client, state, checkpoint)
            print(json.dumps({"domain": domain, "since": state["since"], "until": state["until"],
                              "selected": len(state["company_ids"]), "apply": args.apply}), flush=True)
            results = await recover(RequisiteService(client, EGRClient()), state, checkpoint,
                                    apply=args.apply, limit=args.limit)
            for result in results:
                print(json.dumps(result, ensure_ascii=False), flush=True)
            print(json.dumps({"processed": state["next_index"], "previewed": state["preview_index"],
                              "total": len(state["company_ids"])}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--since", required=True, help="ISO timestamp; timezone-less means Europe/Minsk")
    parser.add_argument("--until")
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--accept-portal-events", action="store_true",
                        help="Acknowledge native Bitrix events/robots cannot be globally silenced")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    logging.basicConfig(level=logging.WARNING)
    # The script's output is restricted to IDs, field names and counters.
    logging.getLogger("app.bitrix").setLevel(logging.CRITICAL)
    try:
        asyncio.run(run(args))
    except Exception as error:
        # No raw HTTP bodies, payloads or credentials in reports.
        print(json.dumps({"status": "stopped", "error_type": type(error).__name__,
                          "message": "Checkpoint preserved. Check OAuth settings, source availability and preview/approval flags."}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
