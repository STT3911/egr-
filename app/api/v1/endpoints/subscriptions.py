"""Подписки пользователя на события компаний (веб-сессия или API-ключ)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.database.models import User, CompanySubscription
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
