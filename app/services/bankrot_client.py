"""HTTP client for bankrot.gov.by /v1 API.

Документация API: скрыта за авторизацией (OpenID Connect).
Базовый URL: https://api.bankrot.gov.by/v1
Авторизация: Bearer token в заголовке Authorization.

Основные эндпоинты:
  POST /cases                          — список дел (с пагинацией)
  GET  /cases/{id}                     — детальная карточка дела
  GET  /cases/{id}/judgements/group    — судебные решения по делу

Структура запроса POST /cases:
  {
    "pagination": {"offset": 0, "count": 100},
    "sort":       {"sortOrder": "asc"},
    "filters":    {...}                   # необязательно
  }

Структура ответа POST /cases:
  {
    "items":      [...],     # список объектов-кейсов на текущей странице
    "count":      1234       # или "totalCount" — общее число записей
  }

Допущение: пагинация работает через offset+count.
Если API изменит формат, достаточно поправить BankrotClient.get_cases_page()
и iter_all_cases().
"""
from __future__ import annotations

import time
from typing import Any, Dict, Iterator, Optional

import httpx

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("bankrot.client")

_DEFAULT_BASE_URL = "https://api.bankrot.gov.by/v1"


class BankrotAPIError(Exception):
    """Ошибка при работе с bankrot.gov.by API."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class BankrotClient:
    """Синхронный HTTP-клиент для bankrot.gov.by /v1 API.

    Использует httpx.Client (синхронный) — совместим с Celery-воркерами
    без дополнительного event-loop.

    Args:
        base_url:    базовый URL API (по умолчанию из настроек или константа)
        token:       Bearer-токен (по умолчанию из BANKROT_API_TOKEN)
        timeout:     таймаут HTTP-запроса в секундах
        max_retries: максимальное число попыток при сетевых ошибках
        retry_delay: базовая задержка между попытками (экспоненциальный backoff)
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        retry_delay: Optional[float] = None,
    ) -> None:
        self.base_url = (
            base_url
            or getattr(settings, "BANKROT_API_URL", _DEFAULT_BASE_URL)
        ).rstrip("/")

        self._token = token or getattr(settings, "BANKROT_API_TOKEN", None)
        self._timeout = timeout or getattr(settings, "BANKROT_TIMEOUT_SECONDS", 30.0)
        self._max_retries = max_retries or getattr(settings, "BANKROT_MAX_RETRIES", 3)
        self._retry_delay = retry_delay or getattr(settings, "BANKROT_RETRY_DELAY_SECONDS", 2.0)

        headers: Dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        else:
            logger.debug(
                "BANKROT_API_TOKEN not set — syncing without authorization "
                "(public read access)."
            )

        self._client = httpx.Client(
            timeout=self._timeout,
            follow_redirects=True,
            headers=headers,
        )

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BankrotClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Выполнить HTTP-запрос с retry-логикой.

        Retry применяется при сетевых ошибках и 5xx ответах.
        Ошибки авторизации (401/403) не ретраятся и выбрасывают
        BankrotAPIError сразу.
        """
        url = f"{self.base_url}{path}"
        last_exc: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                resp = self._client.request(method, url, **kwargs)

                # Auth errors — не ретраим, сразу пробрасываем
                if resp.status_code in (401, 403):
                    raise BankrotAPIError(
                        f"Auth error HTTP {resp.status_code} for {method} {path}. "
                        "Check BANKROT_API_TOKEN in .env",
                        status_code=resp.status_code,
                    )

                # 404 — ресурс не найден (не ретраим)
                if resp.status_code == 404:
                    raise BankrotAPIError(
                        f"Not found: {method} {path}",
                        status_code=404,
                    )

                resp.raise_for_status()

                try:
                    return resp.json()
                except Exception as exc:
                    raise BankrotAPIError(
                        f"Invalid JSON from {method} {path} (status={resp.status_code}): {exc}",
                        status_code=resp.status_code,
                    ) from exc

            except BankrotAPIError:
                raise  # auth/404 — сразу наверх

            except (
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.RemoteProtocolError,
                httpx.ReadError,
            ) as exc:
                last_exc = exc
                logger.warning(
                    "Bankrot API network error attempt %d/%d [%s %s]: %s",
                    attempt, self._max_retries, method, path, exc,
                )

            except httpx.HTTPStatusError as exc:
                last_exc = exc
                logger.warning(
                    "Bankrot API HTTP error attempt %d/%d [%s %s]: HTTP %s",
                    attempt, self._max_retries, method, path,
                    exc.response.status_code,
                )

            if attempt < self._max_retries:
                delay = self._retry_delay * attempt  # линейный backoff: 2s, 4s, 6s…
                logger.debug("Bankrot retry in %.1fs (attempt %d/%d)…", delay, attempt, self._max_retries)
                time.sleep(delay)

        raise BankrotAPIError(
            f"All {self._max_retries} attempts failed for {method} {path}: {last_exc}"
        ) from last_exc

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def get_cases_page(
        self,
        offset: int = 0,
        count: int = 100,
        filters: Optional[Dict[str, Any]] = None,
        sort_order: str = "asc",
    ) -> Dict[str, Any]:
        """POST /cases — одна страница списка дел.

        Returns:
            dict с ключами:
              "items"      — list[dict], объекты дел на текущей странице
              "count"      — int, общее число дел (также может быть "totalCount")
        """
        payload: Dict[str, Any] = {
            "pagination": {"offset": offset, "count": count},
            "sort": {"sortOrder": sort_order},
        }
        if filters:
            payload["filters"] = filters

        return self._request("POST", "/cases", json=payload)

    def iter_all_cases(
        self,
        page_size: int = 100,
        filters: Optional[Dict[str, Any]] = None,
        delay: float = 0.5,
    ) -> Iterator[Dict[str, Any]]:
        """Итератор по всем делам с автоматической пагинацией.

        Допущения:
          - ответ содержит "items" (list) и "count"/"totalCount" (int)
          - пагинация работает через offset; стоп — когда items пуст
            или offset >= total

        Yields:
            dict — отдельный объект дела из API
        """
        offset = 0
        page_num = 0

        while True:
            page_num += 1
            logger.info(
                "Bankrot: fetching page %d (offset=%d, page_size=%d)…",
                page_num, offset, page_size,
            )

            data = self.get_cases_page(offset=offset, count=page_size, filters=filters)

            items: list = data.get("items") or []
            # API может вернуть "count" или "totalCount"
            total: int = (
                data.get("totalCount")
                or data.get("count")
                or 0
            )

            logger.info(
                "Bankrot: page %d — got %d items (total reported=%s)",
                page_num, len(items), total,
            )

            if not items:
                logger.info(
                    "Bankrot: empty page — pagination done after %d pages", page_num - 1
                )
                break

            for item in items:
                yield item

            offset += len(items)

            # Останавливаемся, когда получили все записи
            if total and offset >= total:
                logger.info(
                    "Bankrot: reached total=%d — pagination complete", total
                )
                break

            if delay > 0:
                time.sleep(delay)

    def get_case_detail(self, case_id: int) -> Dict[str, Any]:
        """GET /cases/{id} — детальная карточка дела."""
        return self._request("GET", f"/cases/{case_id}")

    def get_case_judgements_group(self, case_id: int) -> Dict[str, Any]:
        """GET /cases/{id}/judgements/group — судебные решения по делу."""
        return self._request("GET", f"/cases/{case_id}/judgements/group")
