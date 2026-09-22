"""Bounded, fair selection for missing, stale and previously empty source rows."""
from datetime import datetime, timedelta
import json

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.database.models import Company, CompanyPlaceLocation, GrpTaxpayerData, SourceFetchAttempt


def record_source_health(db, source: str, result: dict) -> None:
    """Small durable health record; an attempt timestamp is not data freshness."""
    from app.database.models import SystemState

    value = json.dumps({**result, "checked_at": datetime.utcnow().isoformat()}, default=str)
    stmt = insert(SystemState).values(key=f"source_health:{source}", value=value)
    db.execute(stmt.on_conflict_do_update(index_elements=[SystemState.key],
                                         set_={"value": stmt.excluded.value, "updated_at": datetime.utcnow()}))
    db.commit()


def select_due_unps(db, source: str, limit: int, refresh_days: int, now=None) -> list[int]:
    model = {"place_locations": CompanyPlaceLocation, "grp": GrpTaxpayerData}[source]
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=max(1, refresh_days))
    limit = max(1, limit)
    attempt = SourceFetchAttempt
    eligible = or_(model.unp.is_(None), model.fetched_at.is_(None), model.fetched_at <= cutoff)
    base = (
        select(Company.unp)
        .outerjoin(model, model.unp == Company.unp)
        .outerjoin(attempt, and_(attempt.source == source, attempt.unp == Company.unp))
    )
    # Reserve room for retries AND refreshes. A growing missing backlog must
    # not starve either; failed low UNPs must not monopolize the next batch.
    unseen = base.where(attempt.unp.is_(None), model.unp.is_(None)).order_by(Company.unp)
    stale = base.where(attempt.unp.is_(None), model.unp.is_not(None), eligible).order_by(Company.unp)
    retry = base.where(attempt.next_check_at <= now, eligible).order_by(attempt.next_check_at, Company.unp)
    result: list[int] = []
    quota = max(1, limit // 3)
    for query in (retry, stale, unseen):
        if len(result) >= limit:
            break
        result.extend(int(u) for u in db.execute(query.limit(min(quota, limit - len(result)))).scalars())
    # Fill unused quotas, but only within the original request budget.
    for query in (unseen, stale, retry):
        if len(result) >= limit:
            break
        result.extend(int(u) for u in db.execute(
            query.where(Company.unp.not_in(result)).limit(limit - len(result))
        ).scalars())
    return result


def record_attempt(db, source: str, unp: int, status: str, *, refresh_days: int,
                   empty_days: int = 7, error_minutes: int = 30, now=None) -> None:
    if status not in {"success", "empty", "error"}:
        raise ValueError(f"Invalid fetch status: {status}")
    now = now or datetime.utcnow()
    delay = (timedelta(days=max(1, refresh_days)) if status == "success" else
             timedelta(days=max(1, empty_days)) if status == "empty" else
             timedelta(minutes=max(1, error_minutes)))
    stmt = insert(SourceFetchAttempt).values(
        source=source, unp=unp, status=status, checked_at=now, next_check_at=now + delay,
    )
    db.execute(stmt.on_conflict_do_update(
        index_elements=[SourceFetchAttempt.source, SourceFetchAttempt.unp],
        set_={key: getattr(stmt.excluded, key) for key in ("status", "checked_at", "next_check_at")},
    ))
