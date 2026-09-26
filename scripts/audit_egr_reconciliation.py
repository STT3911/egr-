"""Read-only rehearsal of cached history for every UNP in an EGR date window.

Calls the eight public feeds; never writes business rows, checkpoints or files.
Missing cached snapshots are reported separately, not counted as passing.
"""
import argparse
import asyncio
from datetime import date, timedelta
import json
import logging
from pathlib import Path
import sys
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.core.database import SessionLocal
from app.core.config import settings
from app.database.models import (Company, RawCompanyData, CompanyAddressHistory,
    CompanyNameHistory, CompanyVEDHistory, CompanyContactHistory, CompanyPlaceLocation)
from app.services.egr_client import EGRClient
from app.services.egr_period_sync import collect_day
from app.services.mapper_service import CompanyMapper
from app.crud.company import CompanyCRUD

MODELS = [(CompanyAddressHistory, "addresses", "_save_addresses_history"),
          (CompanyNameHistory, "names", "_save_names_history"),
          (CompanyVEDHistory, "ved", "_save_ved_history"),
          (CompanyContactHistory, "contacts", "_save_contacts_history")]


async def audit(start, end, database):
    if start > end:
        raise ValueError("Invalid date window")
    with SessionLocal() as db:
        if db.execute(text("SELECT current_database()")).scalar_one() != database:
            raise RuntimeError("Unexpected database")
    unps = set()
    client = EGRClient(settings.EGR_API_URL)
    try:
        day = start
        while day <= end:
            pending = await collect_day(client, day, delay=settings.EGR_PERIOD_REQUEST_DELAY)
            unps.update(pending["unps"])
            print(json.dumps({"day": str(day), "companies": len(pending["unps"])}), flush=True)
            day += timedelta(days=1)
    finally:
        await client.close()
    unps = sorted(unps)
    checked, missing, failures = 0, 0, []
    for offset in range(0, len(unps), 100):
        with SessionLocal() as db:
            db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            db.execute(text("SET LOCAL statement_timeout='30s'"))
            batch = unps[offset:offset + 100]
            companies = {c.unp: c for c in db.query(Company).filter(Company.unp.in_(batch))}
            raw = {r.unp: r for r in db.query(RawCompanyData).filter(RawCompanyData.unp.in_(batch))}
            histories = {}
            for model, _, _ in MODELS:
                grouped = {}
                for r in db.query(model).filter(model.company_id.in_([c.id for c in companies.values()])):
                    grouped.setdefault(r.company_id, []).append(r)
                histories[model] = grouped
            for unp in batch:
                if unp not in companies or unp not in raw or not raw[unp].get_data():
                    missing += 1
                    continue
                company = companies[unp]
                rows = {m: [m(**{c.name: getattr(r, c.name) for c in m.__table__.columns})
                            for r in histories[m].get(company.id, [])] for m, _, _ in MODELS}
                fake = Mock()
                def query(model):
                    q = Mock()
                    if model is CompanyPlaceLocation:
                        q.filter.return_value.first.return_value = None
                    else:
                        q.filter.return_value.all.return_value = rows[model]
                    return q
                fake.query.side_effect = query
                fake.add.side_effect = lambda row: rows[type(row)].append(row)
                fake.delete.side_effect = AssertionError("Deletion prohibited")
                crud = CompanyCRUD(fake)
                def snapshot():
                    return repr([[{c.name: getattr(r, c.name) for c in m.__table__.columns}
                                  for r in rows[m]] for m, _, _ in MODELS])
                try:
                    mapped = CompanyMapper().map_to_db_structure(unp, raw[unp].get_data())
                    for m, field, method in MODELS:
                        getattr(crud, method)(company, mapped.get(field, []))
                    first = snapshot()
                    for m, field, method in MODELS:
                        getattr(crud, method)(company, list(reversed(mapped.get(field, []))))
                    if snapshot() != first:
                        raise AssertionError("Non-idempotent history import")
                    checked += 1
                except Exception as exc:
                    failures.append({"unp": unp, "type": type(exc).__name__, "stage": method})
            db.rollback()
    result = {"unique_companies": len(unps), "checked_cached": checked,
              "missing_cached": missing, "failures": failures}
    print(json.dumps(result), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-from", type=date.fromisoformat, required=True)
    parser.add_argument("--date-to", type=date.fromisoformat, required=True)
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    result = asyncio.run(audit(args.date_from, args.date_to, args.database))
    raise SystemExit(1 if result["failures"] else 0)
