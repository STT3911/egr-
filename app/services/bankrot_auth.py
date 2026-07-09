"""OIDC-токен-менеджер для bankrot.gov.by.

Проблема: access-токен клиента `ersb_frontend` живёт ~24 часа, поэтому
статический `BANKROT_API_TOKEN` из devtools протухает за сутки и ежедневный
синк начинает падать с 401.

Решение: если задан `BANKROT_REFRESH_TOKEN` (scope offline_access), меняем его
на свежий access-токен через POST /connect/token (grant_type=refresh_token).
Сервер IdentityServer ротирует refresh-токен на каждый обмен, поэтому новый
refresh сохраняем на диск и используем впредь.

Порядок получения refresh-токена (разово, вручную):
  1. Войти на https://bankrot.gov.by через браузер.
  2. DevTools → Application → Local Storage → ключ
     `oidc.user:https://account.bankrot.gov.by:ersb_frontend`.
  3. Скопировать поле `refresh_token` в .env → BANKROT_REFRESH_TOKEN.

Если refresh-токен не задан — менеджер отдаёт статический BANKROT_API_TOKEN
как есть (обратная совместимость).
"""
from __future__ import annotations

import base64
import json
import threading
import time
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("bankrot.auth")

# За сколько секунд до истечения access-токена обновляем его заранее.
_EXP_SKEW_SECONDS = 120


def _decode_jwt_exp(token: str) -> Optional[int]:
    """Вернуть unix-время истечения (exp) из JWT без проверки подписи, либо None."""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = payload.get("exp")
        return int(exp) if exp is not None else None
    except Exception:
        return None


class BankrotTokenManager:
    """Отдаёт валидный Bearer-токен, обновляя его через refresh_token при необходимости.

    Потокобезопасен (Celery-воркер может дёргать из нескольких гринлетов/потоков).
    Кэширует access-токен в памяти процесса.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._access_token: Optional[str] = getattr(settings, "BANKROT_API_TOKEN", None)
        self._access_exp: Optional[int] = (
            _decode_jwt_exp(self._access_token) if self._access_token else None
        )
        self._refresh_token: Optional[str] = self._load_refresh_token()

    # ------------------------------------------------------------------
    # refresh-token persistence
    # ------------------------------------------------------------------

    def _refresh_file(self) -> Path:
        return Path(getattr(settings, "BANKROT_REFRESH_TOKEN_FILE", "data/bankrot/refresh_token"))

    def _load_refresh_token(self) -> Optional[str]:
        # Приоритет у ротированного токена на диске — он свежее, чем в .env.
        f = self._refresh_file()
        try:
            if f.exists():
                saved = f.read_text(encoding="utf-8").strip()
                if saved:
                    return saved
        except Exception as exc:
            logger.warning("Не удалось прочитать сохранённый refresh-токен: %s", exc)
        return getattr(settings, "BANKROT_REFRESH_TOKEN", None)

    def _save_refresh_token(self, token: str) -> None:
        f = self._refresh_file()
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(token, encoding="utf-8")
        except Exception as exc:
            logger.warning("Не удалось сохранить ротированный refresh-токен: %s", exc)

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    @property
    def has_refresh(self) -> bool:
        return bool(self._refresh_token)

    def _expired(self) -> bool:
        if not self._access_token:
            return True
        if self._access_exp is None:
            return False  # не JWT / не смогли распарсить — считаем валидным, полагаемся на 401
        return time.time() >= (self._access_exp - _EXP_SKEW_SECONDS)

    def get_token(self, force_refresh: bool = False) -> Optional[str]:
        """Вернуть валидный access-токен, обновив через refresh при необходимости."""
        with self._lock:
            if not self._refresh_token:
                return self._access_token  # статический режим
            if force_refresh or self._expired():
                self._do_refresh()
            return self._access_token

    def _do_refresh(self) -> None:
        """Обменять refresh_token на новый access (+ ротированный refresh)."""
        assert self._refresh_token is not None
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": getattr(settings, "BANKROT_OIDC_CLIENT_ID", "ersb_frontend"),
        }
        url = getattr(settings, "BANKROT_OIDC_TOKEN_URL",
                      "https://account.bankrot.gov.by/connect/token")
        try:
            resp = httpx.post(
                url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=getattr(settings, "BANKROT_TIMEOUT_SECONDS", 30.0),
            )
        except Exception as exc:
            logger.error("Bankrot refresh: сетевая ошибка обмена токена: %s", exc)
            return

        if resp.status_code != 200:
            logger.error(
                "Bankrot refresh: обмен не удался (HTTP %s): %s. "
                "refresh_token, вероятно, истёк — нужно обновить BANKROT_REFRESH_TOKEN.",
                resp.status_code, resp.text[:300],
            )
            return

        body = resp.json()
        new_access = body.get("access_token")
        new_refresh = body.get("refresh_token")
        if new_access:
            self._access_token = new_access
            self._access_exp = _decode_jwt_exp(new_access)
            logger.info("Bankrot refresh: получен свежий access-токен (exp=%s)", self._access_exp)
        if new_refresh and new_refresh != self._refresh_token:
            self._refresh_token = new_refresh
            self._save_refresh_token(new_refresh)


# Синглтон на процесс — один кэш токена на воркер.
_manager: Optional[BankrotTokenManager] = None
_manager_lock = threading.Lock()


def get_token_manager() -> BankrotTokenManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = BankrotTokenManager()
    return _manager
