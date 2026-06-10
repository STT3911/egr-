"""Подписки пользователя на события компаний (веб-сессия или API-ключ)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.database.models import User, CompanySubscription, SubscriptionEvent
from app.services.auth import get_current_user
from app.services.subscription_events import ALL_EVENT_TYPES

router = APIRouter()


class SubscriptionIn(BaseModel):
    unp: int
    # пустой список = все типы событий
    event_types: list[str] = Field(default_factory=list)


def _validate_event_types(types: list[str]) -> list[str]:
    bad = [t for t in types if t not in ALL_EVENT_TYPES]
    if bad:
        raise HTTPException(status_code=422, detail=f"Неизвестные типы событий: {bad}. Допустимо: {sorted(ALL_EVENT_TYPES)}")
    # дедуп с сохранением порядка
    return list(dict.fromkeys(types))


def _out(s: CompanySubscription) -> dict:
    return {
        "id": str(s.id),
        "unp": s.unp,
        "event_types": s.event_types or [],
        "source": s.source,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.post("/")
def create_subscription(body: SubscriptionIn, request_source: str = "web",
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    event_types = _validate_event_types(body.event_types)
    sub = (
        db.query(CompanySubscription)
        .filter(CompanySubscription.user_id == user.id, CompanySubscription.unp == body.unp)
        .first()
    )
    if sub:
        # повторная подписка на ту же компанию — обновляем набор типов
        sub.event_types = event_types
    else:
        sub = CompanySubscription(user_id=user.id, unp=body.unp, event_types=event_types, source=request_source)
        db.add(sub)
    db.commit()
    db.refresh(sub)
    return _out(sub)


@router.get("/")
def list_subscriptions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    subs = (
        db.query(CompanySubscription)
        .filter(CompanySubscription.user_id == user.id)
        .order_by(CompanySubscription.created_at.desc())
        .all()
    )
    return {"items": [_out(s) for s in subs]}


@router.delete("/{subscription_id}")
def delete_subscription(subscription_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sub = (
        db.query(CompanySubscription)
        .filter(CompanySubscription.id == subscription_id, CompanySubscription.user_id == user.id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Подписка не найдена")
    db.delete(sub)
    db.commit()
    return {"ok": True}


@router.get("/event-types")
def list_event_types():
    """Справочник доступных типов событий — для формы подписки на фронте."""
    return {"event_types": sorted(ALL_EVENT_TYPES)}


# ---------------------------------------------------------------------------
# Пуллинг событий: клиент забирает свои сработавшие события и подтверждает
# обработку (processed_at). Сброс processed_at=NULL → событие выдастся снова.
# ---------------------------------------------------------------------------
def _event_out(e: SubscriptionEvent) -> dict:
    return {
        "id": e.id,
        "unp": e.unp,
        "event_type": e.event_type,
        "old_value": e.old_value,
        "new_value": e.new_value,
        "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
        "processed_at": e.processed_at.isoformat() if e.processed_at else None,
    }


class AckIn(BaseModel):
    # подтвердить конкретные id, ИЛИ всё до up_to_id включительно
    ids: list[int] = Field(default_factory=list)
    up_to_id: int | None = None


@router.get("/events")
def poll_events(
    limit: int = 100,
    include_processed: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Забрать события по своим подпискам. По умолчанию — только необработанные
    (processed_at IS NULL), по возрастанию id. Курсор у клиента — последний id.
    """
    limit = min(max(limit, 1), 1000)
    q = db.query(SubscriptionEvent).filter(SubscriptionEvent.user_id == user.id)
    if not include_processed:
        q = q.filter(SubscriptionEvent.processed_at.is_(None))
    rows = q.order_by(SubscriptionEvent.id.asc()).limit(limit).all()
    return {"count": len(rows), "items": [_event_out(e) for e in rows]}


@router.post("/events/ack")
def ack_events(body: AckIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Пометить события обработанными (processed_at=now). Только свои."""
    q = db.query(SubscriptionEvent).filter(
        SubscriptionEvent.user_id == user.id,
        SubscriptionEvent.processed_at.is_(None),
    )
    if body.ids:
        q = q.filter(SubscriptionEvent.id.in_(body.ids))
    elif body.up_to_id is not None:
        q = q.filter(SubscriptionEvent.id <= body.up_to_id)
    else:
        raise HTTPException(status_code=422, detail="Укажите ids или up_to_id")
    n = q.update({SubscriptionEvent.processed_at: datetime.now()}, synchronize_session=False)
    db.commit()
    return {"acknowledged": n}
