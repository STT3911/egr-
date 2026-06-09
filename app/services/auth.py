"""
Авторизация пользователей-подписчиков.

Без внешних зависимостей (bcrypt/jwt не в requirements):
- пароли: PBKDF2-HMAC-SHA256 (stdlib);
- сессия сайта: HMAC-подписанный токен в cookie (как в admin);
- API-доступ: per-account ключ (храним sha256(key)).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.status import HTTP_401_UNAUTHORIZED

from app.core.config import settings
from app.core.database import get_db
from app.database.models import User, ApiKey

USER_COOKIE_NAME = "egr_user_session"
USER_SESSION_TTL_HOURS = 24 * 30  # 30 дней
PBKDF2_ITERATIONS = 200_000


# --- Пароли --------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


# --- Сессия сайта (cookie) ----------------------------------------------
def _session_secret() -> str:
    return settings.SECRET_KEY or settings.ADMIN_PASSWORD_HASH or "change-me-user-session-secret"


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign(payload: str) -> str:
    return hmac.new(_session_secret().encode("utf-8"), payload.encode("ascii"), hashlib.sha256).hexdigest()


def create_user_session(user_id: str) -> str:
    payload = {"sub": str(user_id), "exp": int(time.time()) + USER_SESSION_TTL_HOURS * 3600}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(body)}"


def read_user_session(token: str | None) -> dict | None:
    if not token or "." not in token:
        return None
    body, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(signature, _sign(body)):
        return None
    try:
        payload = json.loads(_b64d(body))
    except Exception:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload


# --- API-ключи -----------------------------------------------------------
def generate_api_key() -> str:
    return "egr_" + secrets.token_urlsafe(32)


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


# --- Зависимость текущего пользователя -----------------------------------
def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    Аутентификация по API-ключу (Authorization: Bearer <key>) ИЛИ по сессии сайта.
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        raw = auth[7:].strip()
        ak = (
            db.query(ApiKey)
            .filter(ApiKey.key_hash == hash_api_key(raw), ApiKey.revoked.is_(False))
            .first()
        )
        if ak:
            user = db.query(User).filter(User.id == ak.user_id, User.is_active.is_(True)).first()
            if user:
                return user
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    payload = read_user_session(request.cookies.get(USER_COOKIE_NAME))
    if payload:
        user = db.query(User).filter(User.id == payload["sub"], User.is_active.is_(True)).first()
        if user:
            return user
    raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Authentication required")
