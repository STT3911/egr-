"""OIDC-токен-менеджер для публичного API bankrot.gov.by."""
from __future__ import annotations

import base64
import json
import re
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import httpx

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("bankrot.auth")

# За сколько секунд до истечения access-токена обновляем его заранее.
_EXP_SKEW_SECONDS = 120
_SCRIPT_SRC_RE = re.compile(r"<script[^>]+src=[\"']([^\"']+\.js[^\"']*)[\"']", re.I)
_CONFIG_MODULE_RE = re.compile(r"[\"'](\.?/[^\"']*config(?:\.release)?-[^\"']+\.js)[\"']", re.I)
_CLIENT_ID_RE = re.compile(r"ClientId\s*:\s*[\"']([^\"']+)[\"']")
_CLIENT_SECRET_RE = re.compile(r"ClientSecret\s*:\s*[\"']([^\"']+)[\"']")


class BankrotAuthError(RuntimeError):
    """Авторизация Bankrot не может выдать действующий access-токен."""


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
    """Отдаёт Bearer-токен, автоматически продлевая его через публичный OIDC-клиент.

    Потокобезопасен (Celery-воркер может дёргать из нескольких гринлетов/потоков).
    Кэширует access-токен в памяти процесса.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._access_token: Optional[str] = getattr(settings, "BANKROT_API_TOKEN", None)
        self._access_exp: Optional[int] = (
            _decode_jwt_exp(self._access_token) if self._access_token else None
        )
        self._configured_refresh_token: Optional[str] = getattr(
            settings, "BANKROT_REFRESH_TOKEN", None
        )
        self._refresh_token: Optional[str] = self._load_refresh_token()
        self._client_secret: Optional[str] = getattr(
            settings, "BANKROT_OIDC_CLIENT_SECRET", None
        )

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
        return self._configured_refresh_token

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

    @property
    def can_renew(self) -> bool:
        return True

    def _expired(self) -> bool:
        if not self._access_token:
            return True
        if self._access_exp is None:
            return False  # не JWT / не смогли распарсить — считаем валидным, полагаемся на 401
        return time.time() >= (self._access_exp - _EXP_SKEW_SECONDS)

    def get_token(self, force_refresh: bool = False) -> str:
        """Вернуть валидный access-токен, обновив его без участия пользователя."""
        with self._lock:
            if force_refresh or self._expired():
                if self._refresh_token:
                    try:
                        self._do_refresh()
                    except BankrotAuthError as exc:
                        logger.warning(
                            "Bankrot refresh-token недоступен, использую публичный "
                            "client_credentials: %s",
                            exc,
                        )
                        self._do_client_credentials()
                else:
                    self._do_client_credentials()
            if not self._access_token:
                raise BankrotAuthError("Bankrot token endpoint не выдал access_token")
            return self._access_token

    def _discover_client_secret(self) -> str:
        frontend_url = getattr(settings, "BANKROT_FRONTEND_URL", "https://bankrot.gov.by")
        timeout = getattr(settings, "BANKROT_TIMEOUT_SECONDS", 30.0)
        try:
            html_response = httpx.get(frontend_url, timeout=timeout, follow_redirects=True)
            html_response.raise_for_status()
            script_urls = [
                urljoin(str(html_response.url), path)
                for path in _SCRIPT_SRC_RE.findall(html_response.text)
            ]
            for script_url in script_urls:
                script_response = httpx.get(script_url, timeout=timeout, follow_redirects=True)
                script_response.raise_for_status()
                client_id_match = _CLIENT_ID_RE.search(script_response.text)
                secret_match = _CLIENT_SECRET_RE.search(script_response.text)
                expected_client_id = getattr(settings, "BANKROT_OIDC_CLIENT_ID", "ersb_frontend")
                if (
                    client_id_match
                    and secret_match
                    and client_id_match.group(1) == expected_client_id
                ):
                    self._client_secret = secret_match.group(1)
                    return self._client_secret
                config_match = _CONFIG_MODULE_RE.search(script_response.text)
                if not config_match:
                    continue
                config_url = urljoin(str(script_response.url), config_match.group(1))
                config_response = httpx.get(config_url, timeout=timeout, follow_redirects=True)
                config_response.raise_for_status()
                client_id_match = _CLIENT_ID_RE.search(config_response.text)
                secret_match = _CLIENT_SECRET_RE.search(config_response.text)
                if (
                    client_id_match
                    and secret_match
                    and client_id_match.group(1) == expected_client_id
                ):
                    self._client_secret = secret_match.group(1)
                    return self._client_secret
        except Exception as exc:
            raise BankrotAuthError(
                f"не удалось прочитать публичную OIDC-конфигурацию Bankrot: {exc}"
            ) from exc
        raise BankrotAuthError(
            "в публичной frontend-конфигурации Bankrot не найден OIDC client secret"
        )

    def _do_client_credentials(self) -> None:
        client_secret = self._client_secret or self._discover_client_secret()
        data = {
            "grant_type": "client_credentials",
            "client_id": getattr(settings, "BANKROT_OIDC_CLIENT_ID", "ersb_frontend"),
            "client_secret": client_secret,
            "scope": getattr(settings, "BANKROT_OIDC_SCOPE", "ersb_backend.api"),
        }
        url = getattr(
            settings,
            "BANKROT_OIDC_TOKEN_URL",
            "https://account.bankrot.gov.by/connect/token",
        )
        try:
            response = httpx.post(
                url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=getattr(settings, "BANKROT_TIMEOUT_SECONDS", 30.0),
            )
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            raise BankrotAuthError(
                f"Bankrot client_credentials не выдал токен: {exc}"
            ) from exc
        access_token = body.get("access_token")
        if not access_token:
            raise BankrotAuthError(
                "Bankrot client_credentials вернул ответ без access_token"
            )
        self._access_token = access_token
        self._access_exp = _decode_jwt_exp(access_token)
        logger.info(
            "Bankrot client_credentials: получен access-токен (exp=%s)",
            self._access_exp,
        )

    def _do_refresh(self, *, allow_configured_fallback: bool = True) -> None:
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
            raise BankrotAuthError(
                f"Bankrot refresh-token: сетевая ошибка обмена: {exc}"
            ) from exc

        if resp.status_code != 200:
            configured = self._configured_refresh_token
            if (
                allow_configured_fallback
                and configured
                and configured != self._refresh_token
            ):
                logger.warning(
                    "Сохранённый Bankrot refresh-токен отклонён (HTTP %s); "
                    "повторяю с BANKROT_REFRESH_TOKEN из .env",
                    resp.status_code,
                )
                self._refresh_token = configured
                self._do_refresh(allow_configured_fallback=False)
                return
            logger.error(
                "Bankrot refresh: обмен не удался (HTTP %s): %s. "
                "refresh_token, вероятно, истёк — нужно обновить BANKROT_REFRESH_TOKEN.",
                resp.status_code, resp.text[:300],
            )
            raise BankrotAuthError(
                "Bankrot refresh-token отклонён "
                f"(HTTP {resp.status_code}): {resp.text[:200]}"
            )

        body = resp.json()
        new_access = body.get("access_token")
        new_refresh = body.get("refresh_token")
        if not new_access:
            raise BankrotAuthError(
                "Bankrot token endpoint вернул HTTP 200 без access_token"
            )
        self._access_token = new_access
        self._access_exp = _decode_jwt_exp(new_access)
        logger.info("Bankrot refresh: получен свежий access-токен (exp=%s)", self._access_exp)
        if new_refresh:
            self._refresh_token = new_refresh
        if self._refresh_token:
            self._save_refresh_token(self._refresh_token)


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
