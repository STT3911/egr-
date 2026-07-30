"""Авторизация пользователей-подписчиков + управление API-ключами."""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.database.models import User, ApiKey
from app.services.auth import (
    USER_COOKIE_NAME,
    USER_SESSION_TTL_HOURS,
    hash_password,
    verify_password,
    create_user_session,
    generate_api_key,
    hash_api_key,
    generate_webhook_secret,
    get_current_user,
)
from app.services.telegram_link import (
    LINK_TTL_SECONDS,
    TelegramLinkUnavailable,
    create_telegram_link,
    revoke_telegram_links,
)

router = APIRouter()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    email: str
    password: str


class ApiKeyIn(BaseModel):
    label: str | None = None


def _set_session_cookie(response: Response, user_id: str) -> None:
    response.set_cookie(
        key=USER_COOKIE_NAME,
        value=create_user_session(user_id),
        max_age=USER_SESSION_TTL_HOURS * 3600,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


def _user_out(u: User) -> dict:
    return {"id": str(u.id), "email": u.email, "telegram_id": u.telegram_id}


@router.post("/register")
def register(body: RegisterIn, response: Response, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Некорректный email")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    _set_session_cookie(response, user.id)
    return _user_out(user)


@router.post("/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.query(User).filter(User.email == email, User.is_active.is_(True)).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    _set_session_cookie(response, user.id)
    return _user_out(user)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(USER_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _user_out(user)


# --- Telegram ------------------------------------------------------------
@router.post("/telegram-link")
def create_telegram_connection(user: User = Depends(get_current_user)):
    if user.telegram_id is not None:
        return {
            "linked": True,
            "telegram_id": user.telegram_id,
            "expires_in": None,
            "command": None,
            "bot_url": None,
        }
    try:
        token = create_telegram_link(str(user.id))
    except TelegramLinkUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    command = f"/start link_{token}"
    username = (settings.TELEGRAM_BOT_USERNAME or "").strip().lstrip("@")
    bot_url = (
        f"https://t.me/{username}?start=link_{token}"
        if username
        else None
    )
    return {
        "linked": False,
        "telegram_id": None,
        "expires_in": LINK_TTL_SECONDS,
        "command": command,
        "bot_url": bot_url,
    }


@router.delete("/telegram-link")
def delete_telegram_connection(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        revoke_telegram_links(str(user.id))
    except TelegramLinkUnavailable:
        pass
    user.telegram_id = None
    db.commit()
    return {"ok": True, "linked": False}


# --- API-ключи -----------------------------------------------------------
@router.post("/api-keys")
def create_api_key(body: ApiKeyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    raw = generate_api_key()
    ak = ApiKey(user_id=user.id, key_hash=hash_api_key(raw), label=body.label)
    db.add(ak)
    db.commit()
    db.refresh(ak)
    # Сырой ключ показываем ОДИН раз — в БД хранится только хеш.
    return {"id": str(ak.id), "label": ak.label, "api_key": raw,
            "created_at": ak.created_at.isoformat() if ak.created_at else None}


@router.get("/api-keys")
def list_api_keys(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    keys = db.query(ApiKey).filter(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc()).all()
    return {"items": [
        {"id": str(k.id), "label": k.label, "revoked": k.revoked,
         "created_at": k.created_at.isoformat() if k.created_at else None,
         "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None}
        for k in keys
    ]}


@router.delete("/api-keys/{key_id}")
def revoke_api_key(key_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ak = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == user.id).first()
    if not ak:
        raise HTTPException(status_code=404, detail="Ключ не найден")
    ak.revoked = True
    db.commit()
    return {"ok": True}


# --- Webhook (push-доставка событий на адрес клиента) --------------------
class WebhookIn(BaseModel):
    url: str


def _webhook_out(u: User) -> dict:
    return {
        "webhook_url": u.webhook_url,
        "webhook_secret": u.webhook_secret,  # нужен клиенту для проверки подписи X-EGR-Signature
        "enabled": bool(u.webhook_url),
    }


@router.put("/webhook")
def set_webhook(body: WebhookIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    url = body.url.strip()
    if not (url.startswith("https://") or url.startswith("http://")):
        raise HTTPException(status_code=422, detail="URL должен начинаться с http:// или https://")
    user.webhook_url = url
    if not user.webhook_secret:
        user.webhook_secret = generate_webhook_secret()
    db.commit()
    db.refresh(user)
    return _webhook_out(user)


@router.get("/webhook")
def get_webhook(user: User = Depends(get_current_user)):
    return _webhook_out(user)


@router.delete("/webhook")
def delete_webhook(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.webhook_url = None
    db.commit()
    return {"ok": True, "enabled": False}
