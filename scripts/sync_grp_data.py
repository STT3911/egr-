"""Manual GRP (налоговая) sync.

Usage (inside backend container):
  python scripts/sync_grp_data.py --limit 5000 --only-missing

This script fetches GRP public data for UNPs stored in our DB and upserts into
grp_taxpayer_data.
"""

from __future__ import annotations

import argparse
import asyncio
from typing import List

from app.core.database import SessionLocal
from app.database.models import Company, GrpTaxpayerData
from app.crud.grp import GrpCRUD
from app.services.grp_client import GRPClient


async def _run(unps: List[int], batch_size: int) -> dict:
    client = GRPClient()
    sem = asyncio.Semaphore(10)

    async def _one(u: int):
        async with sem:
            try:
                payload = await client.get_taxpayer(int(u))
                return int(u), payload, 200, None
            except Exception as e:
                return int(u), None, None, str(e)

    try:
        processed = 0
        errors = 0
        results_all = []
        for i in range(0, len(unps), batch_size):
            batch = unps[i:i + batch_size]
            results = await asyncio.gather(*(_one(u) for u in batch))
            results_all.extend(results)
            processed += len(results)
            errors += sum(1 for _, _, _, err in results if err)
        return {"results": results_all, "processed": processed, "errors": errors}
    finally:
        await client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--only-missing", action="store_true", default=False)
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        q = db.query(Company.unp)
        if args.only_missing:
            q = q.outerjoin(GrpTaxpayerData, Company.unp == GrpTaxpayerData.unp).filter(GrpTaxpayerData.unp == None)  # noqa: E711
        unps = [row[0] for row in q.order_by(Company.unp.asc()).limit(args.limit).all()]

        if not unps:
            print("Nothing to sync")
            return

        out = asyncio.run(_run(unps, args.batch_size))
        crud = GrpCRUD(db)
        for u, payload, status, err in out["results"]:
            crud.upsert_from_api(unp=u, payload=payload if isinstance(payload, dict) else None, http_status=status, error=err)
        db.commit()
        print({"processed": out["processed"], "errors": out["errors"], "limit": args.limit, "only_missing": args.only_missing})
    finally:
        db.close()


if __name__ == "__main__":
    main()
