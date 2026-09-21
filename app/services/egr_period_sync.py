"""Daily EGR change feeds with durable per-company progress (no broker-only cursor).

Source contract: https://egr.gov.by/api/v2/api-docs, inspected 2026-09-18.
The caller must hold the dedicated PostgreSQL advisory transaction lock.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import date, timedelta

from app.database.models import SystemState
from app.services.egr_event_notifications import emit_egr_source_events
from app.services.egr_contract import egr_date

logger = logging.getLogger(__name__)
STATE_KEY = "egr_period_sync_v2"
PERIOD_SOURCES = {
    "getBaseInfoByPeriod": ("ngrn",),
    "getEventByPeriod": ("ngrn",),
    "getAddressByPeriod": ("ngrn",),
    "getJurNamesByPeriod": ("ngrn",),
    "getIPFIOByPeriod": ("ngrn",),
    "getVEDByPeriod": ("ngrn",),
    "getShortInfoByPeriod": ("ngrn",),
    "getIPtoJurByPeriod": ("ipngrn", "ulngrn"),
}


def validate_period_rows(source, rows):
    if not isinstance(rows, list):
        raise ValueError(f"{source}: expected a JSON array")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{source}: invalid row")
        for field in PERIOD_SOURCES[source]:
            value = row.get(field)
            if isinstance(value, bool) or not str(value).isdigit() or not 0 < int(value) < 1_000_000_000:
                raise ValueError(f"{source}: invalid {field}")


async def collect_day(client, day, *, delay=0.5, row_limit=2500):
    """Collect all eight feeds before acknowledging ANY part of this day."""
    unps, counts, events, transitions = set(), {}, {}, []
    for source, fields in PERIOD_SOURCES.items():
        await asyncio.sleep(delay)
        rows = await client.get_period_rows(source, day.strftime("%d.%m.%Y"))
        validate_period_rows(source, rows)
        # The old importer observed truncation near 2500; Swagger offers no
        # pagination. Fail conservatively, rather than silently dropping rows.
        if row_limit and len(rows) >= row_limit:
            raise ValueError(f"{source} {day}: possible truncation ({len(rows)} rows)")
        counts[source] = len(rows)
        if source == "getIPtoJurByPeriod":
            transitions = rows
        for row in rows:
            unps.update(int(row[field]) for field in fields)
            if source == "getEventByPeriod":
                events.setdefault(str(int(row["ngrn"])), []).append(row)
    return {"day": day.isoformat(), "unps": sorted(unps), "next_index": 0,
            "counts": counts, "events": events, "transitions": transitions}


class PeriodSyncStore:
    def __init__(self, db):
        self.db = db

    def load(self):
        row = self.db.query(SystemState).filter(SystemState.key == STATE_KEY).first()
        if not row:
            return None
        state = json.loads(row.value)
        if state.get("version") != 2:
            raise ValueError("Unsupported EGR period checkpoint version")
        return state

    def save(self, state, *, unp=None, events=(), day=None, completed_day=None, transitions=()):
        try:
            if transitions:
                from sqlalchemy import func
                from sqlalchemy.dialects.postgresql import insert
                from app.database.models import EGRIPToJur
                for item in transitions:
                    values = dict(ip_unp=int(item["ipngrn"]), jur_unp=int(item["ulngrn"]),
                                  registration_date=egr_date(item.get("dreg")), raw=item)
                    stmt = insert(EGRIPToJur).values(**values)
                    self.db.execute(stmt.on_conflict_do_update(
                        index_elements=[EGRIPToJur.ip_unp, EGRIPToJur.jur_unp],
                        set_={**values, "last_seen_at": func.now()},
                    ))
            if unp is not None and events:
                emit_egr_source_events(self.db, unp, events, fallback_date=day)
            row = self.db.query(SystemState).filter(SystemState.key == STATE_KEY).first()
            value = json.dumps(state, ensure_ascii=False)
            if row:
                row.value = value
            else:
                self.db.add(SystemState(key=STATE_KEY, value=value))
            if completed_day is not None:
                # Compatibility for existing monitoring; never move the old
                # cursor backwards during bootstrap or overlap replay.
                legacy = self.db.query(SystemState).filter(SystemState.key == "egr_last_sync_date").first()
                if not legacy:
                    self.db.add(SystemState(key="egr_last_sync_date", value=completed_day.isoformat()))
                elif date.fromisoformat(legacy.value) < completed_day:
                    legacy.value = completed_day.isoformat()
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise


async def run_period_sync(store, client, refresh, *, target, bootstrap_days=30,
                          overlap_days=3, max_companies=500, max_seconds=1200,
                          delay=0.5, row_limit=2500):
    """Resume a saved window. Acknowledgements follow successful DB processing.

    refresh may commit independently. A crash before acknowledgement replays
    that company (at-least-once), never skips it. Old history is retained.
    """
    if min(bootstrap_days, overlap_days, max_companies) < 1 or max_seconds <= 0 or delay < 0 or row_limit < 0:
        raise ValueError("Invalid EGR period sync limits")
    started = time.monotonic()
    state = store.load()
    if not state or state.get("next_day") is None:
        last = date.fromisoformat(state["completed_target"]) if state else None
        if last and last >= target:
            return {"status": "up_to_date", "target": target.isoformat()}
        start = (min(last + timedelta(days=1), target - timedelta(days=overlap_days - 1))
                 if last else target - timedelta(days=bootstrap_days - 1))
        state = {"version": 2, "target": target.isoformat(), "next_day": start.isoformat(),
                 "pending": None, "completed_target": last.isoformat() if last else None}
        store.save(state)
    processed = 0
    end = date.fromisoformat(state["target"])
    while state["next_day"] and date.fromisoformat(state["next_day"]) <= end:
        if processed >= max_companies or time.monotonic() - started >= max_seconds:
            return {"status": "pending", "processed": processed, "day": state["next_day"]}
        day = date.fromisoformat(state["next_day"])
        if state["pending"] is None:
            state["pending"] = await collect_day(client, day, delay=delay, row_limit=row_limit)
            store.save(state, transitions=state["pending"]["transitions"])
            logger.info("EGR ByPeriod %s: %s; unique_unps=%s", day,
                        state["pending"]["counts"], len(state["pending"]["unps"]))
        pending = state["pending"]
        while pending["next_index"] < len(pending["unps"]):
            if processed >= max_companies or time.monotonic() - started >= max_seconds:
                return {"status": "pending", "processed": processed, "day": day.isoformat()}
            unp = pending["unps"][pending["next_index"]]
            await asyncio.sleep(delay)
            await refresh(unp)
            pending["next_index"] += 1
            store.save(state, unp=unp, events=pending["events"].get(str(unp), []), day=day)
            processed += 1
            logger.info("EGR ByPeriod %s: saved UNP %s (%s/%s)", day, unp,
                        pending["next_index"], len(pending["unps"]))
        state["pending"] = None
        state["last_completed_day"] = day.isoformat()
        state["next_day"] = (day + timedelta(days=1)).isoformat() if day < end else None
        if day == end:
            state["completed_target"] = end.isoformat()
        store.save(state, completed_day=day)
    return {"status": "complete", "processed": processed, "target": end.isoformat()}
