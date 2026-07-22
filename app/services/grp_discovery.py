"""On-demand discovery of taxpayer records absent from the EGR company feed."""

from __future__ import annotations

from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import get_logger
from app.crud.grp import GrpCRUD
from app.database.models import GrpRawData
from app.services.company_registry import sync_company_from_grp
from app.services.grp_client import GRPClient
from app.services.unp_enum import is_valid_unp


logger = get_logger("grp_discovery")


def _is_recent_negative(row: GrpRawData | None) -> bool:
    if row is None or row.http_status not in {400, 404} or row.updated_at is None:
        return False
    cache_minutes = max(1, int(settings.GRP_ON_DEMAND_NEGATIVE_CACHE_MINUTES))
    return row.updated_at >= datetime.now() - timedelta(minutes=cache_minutes)


async def discover_company_from_grp(db: Session, unp: int) -> bool:
    """Fetch one valid UNP from GRP and materialize it in the central registry."""
    unp_text = str(unp)
    if not settings.GRP_ON_DEMAND_ENABLED or not is_valid_unp(unp_text):
        return False

    crud = GrpCRUD(db)
    if crud.get_by_unp(unp) is not None:
        created = sync_company_from_grp(db, unp)
        db.commit()
        return created

    raw = crud.get_raw_by_unp(unp)
    if _is_recent_negative(raw):
        return False

    client = GRPClient(timeout=float(settings.GRP_ON_DEMAND_TIMEOUT_SECONDS))
    try:
        payload = await client.get_taxpayer(unp)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in {400, 404}:
            crud.save_raw_data(unp=unp, raw_json={}, http_status=status)
            db.commit()
            return False
        db.rollback()
        logger.warning("GRP discovery failed for %s: HTTP %s", unp, status)
        return False
    except (httpx.HTTPError, ValueError) as exc:
        db.rollback()
        logger.warning("GRP discovery failed for %s: %s", unp, exc)
        return False
    finally:
        await client.close()

    if not payload:
        crud.save_raw_data(unp=unp, raw_json={}, http_status=404)
        db.commit()
        return False

    returned_unp = payload.get("VUNP") or payload.get("vunp")
    if returned_unp and str(returned_unp) != unp_text:
        db.rollback()
        logger.error("GRP returned mismatched UNP %s for requested %s", returned_unp, unp)
        return False

    try:
        parsed = crud.upsert_from_api(unp=unp, payload=payload, http_status=200)
        if parsed is None or not sync_company_from_grp(db, unp):
            db.rollback()
            return False
        db.commit()
        logger.info("Discovered company %s through GRP", unp)
        return True
    except Exception:
        db.rollback()
        logger.exception("Failed to persist GRP discovery for %s", unp)
        return False
