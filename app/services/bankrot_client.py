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
    "pagination": {"offset": 0, "count": 20},
    "sort":       {"sortOrder": 1},
    "filters":    {...}                   # полный объект обязателен
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
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.logger import get_logger
from app.services.bankrot_auth import get_token_manager

logger = get_logger("bankrot.client")

_DEFAULT_BASE_URL = "https://api.bankrot.gov.by/v1"


@dataclass(frozen=True)
class BankrotCaseDatasetSpec:
    """Описание публичного раздела карточки дела на bankrot.gov.by."""

    name: str
    path: str
    method: str = "POST"
    payload_mode: str = "paginated"


BANKROT_CASE_DATASETS: Tuple[BankrotCaseDatasetSpec, ...] = (
    BankrotCaseDatasetSpec("properties", "/cases/{case_id}/properties"),
    BankrotCaseDatasetSpec(
        "property_reports", "/cases/{case_id}/property-reports", payload_mode="filters"
    ),
    BankrotCaseDatasetSpec(
        "property_valuations", "/cases/{case_id}/property-reports/valuation"
    ),
    BankrotCaseDatasetSpec("sales", "/cases/{case_id}/sales"),
    BankrotCaseDatasetSpec("creditor_meetings", "/cases/{case_id}/meetings"),
    BankrotCaseDatasetSpec("creditor_committees", "/cases/{case_id}/committees"),
    BankrotCaseDatasetSpec(
        "creditor_requirements", "/cases/{case_id}/creditor-requirements"
    ),
    BankrotCaseDatasetSpec(
        "property_write_off", "/cases/{case_id}/property-write-off"
    ),
    BankrotCaseDatasetSpec(
        "transfer_remaining_properties",
        "/cases/{case_id}/transfer-remaining-properties",
    ),
    BankrotCaseDatasetSpec(
        "transfer_unsold_properties", "/cases/{case_id}/transfer-unsold-properties"
    ),
    BankrotCaseDatasetSpec(
        "readjustments", "/cases/{case_id}/readjustments", method="GET", payload_mode="none"
    ),
    BankrotCaseDatasetSpec(
        "fund_balance_reports",
        "/cases/{case_id}/fund-balance-reports",
        method="GET",
        payload_mode="none",
    ),
)

BANKROT_MANAGER_DATASETS: Tuple[BankrotCaseDatasetSpec, ...] = (
    BankrotCaseDatasetSpec(
        "manager_full_info", "/manager/{manager_id}/fullinfo", method="GET"
    ),
    BankrotCaseDatasetSpec(
        "manager_accreditation", "/manager/{manager_id}/accreditation", method="GET"
    ),
    BankrotCaseDatasetSpec(
        "manager_documents", "/manager/{manager_id}/manager-documents", method="GET"
    ),
    BankrotCaseDatasetSpec(
        "manager_education", "/manager/{manager_id}/education", method="GET"
    ),
    BankrotCaseDatasetSpec(
        "manager_debtors", "/manager/debtors/?id={manager_id}", method="GET"
    ),
    BankrotCaseDatasetSpec(
        "manager_bank_accounts", "/manager/{manager_id}/bank-accounts", method="GET"
    ),
    BankrotCaseDatasetSpec(
        "manager_online_wallets", "/manager/{manager_id}/online-wallets", method="GET"
    ),
)

BANKROT_DEBTOR_DATASETS: Tuple[BankrotCaseDatasetSpec, ...] = (
    BankrotCaseDatasetSpec(
        "debtor_bank_accounts", "/debtors/{debtor_id}/bank-accounts", method="GET"
    ),
    BankrotCaseDatasetSpec(
        "debtor_online_wallets", "/debtors/{debtor_id}/online-wallets", method="GET"
    ),
)

_DEFAULT_CASE_FILTERS: Dict[str, Any] = {
    "number": "",
    "status": "",
    "declarantTypes": None,
    "manager": "",
    "procedure": "",
    "start": {"from": None, "to": None},
    "end": {"from": None, "to": None},
    "debtor": {"unp": "", "name": "", "region": "", "type": ""},
}

_DEFAULT_PUBLICATION_FILTERS: Dict[str, Any] = {
    "debtor": "",
    "manager": "",
    "region": "",
    "published": {"from": None, "to": None},
}

_COLLECTION_KEYS = (
    "items",
    "messages",
    "properties",
    "propertyReports",
    "propertyValuations",
    "sales",
    "meetings",
    "committees",
    "requirementsResults",
    "propertiesWriteOff",
    "transferredUnsoldProperty",
)


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

        # Токен-менеджер сам обновляет access через refresh_token (если задан).
        # Явно переданный token имеет приоритет (тесты/ручные вызовы).
        self._explicit_token = token
        self._token_mgr = get_token_manager() if token is None else None
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
        # Authorization выставляется динамически в _apply_auth() перед каждым
        # запросом (токен-менеджер может обновить access-токен между вызовами).
        initial = self._current_token()
        if initial:
            headers["Authorization"] = f"Bearer {initial}"
        elif not (self._token_mgr and self._token_mgr.has_refresh):
            logger.warning(
                "BANKROT_API_TOKEN/REFRESH_TOKEN не заданы — API вернёт 401. "
                "Укажите BANKROT_REFRESH_TOKEN в .env."
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

    def _current_token(self) -> Optional[str]:
        """Актуальный access-токен: явный → через менеджер (с авто-refresh) → статический."""
        if self._explicit_token:
            return self._explicit_token
        if self._token_mgr is not None:
            return self._token_mgr.get_token()
        return self._token

    def _apply_auth(self, force_refresh: bool = False) -> bool:
        """Проставить свежий Bearer в заголовки клиента. True, если токен есть/обновлён."""
        if self._token_mgr is not None:
            token = self._token_mgr.get_token(force_refresh=force_refresh)
        else:
            token = self._explicit_token or self._token
        if token:
            self._client.headers["Authorization"] = f"Bearer {token}"
            return True
        return False

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Выполнить HTTP-запрос с retry-логикой.

        Retry применяется при сетевых ошибках и 5xx ответах.
        При 401 один раз форсим обновление токена через refresh_token и
        повторяем запрос; если и после этого 401/403 — пробрасываем ошибку.
        """
        url = f"{self.base_url}{path}"
        last_exc: Optional[Exception] = None
        reauth_tried = False

        self._apply_auth()

        for attempt in range(1, self._max_retries + 1):
            try:
                resp = self._client.request(method, url, **kwargs)

                # 401 → один раз обновляем токен через refresh и повторяем запрос
                if resp.status_code == 401 and not reauth_tried and self._token_mgr \
                        and self._token_mgr.has_refresh:
                    reauth_tried = True
                    logger.info("Bankrot: 401 — обновляю access-токен через refresh и повторяю")
                    if self._apply_auth(force_refresh=True):
                        continue

                # Auth errors — не ретраим, сразу пробрасываем
                if resp.status_code in (401, 403):
                    raise BankrotAPIError(
                        f"Auth error HTTP {resp.status_code} for {method} {path}. "
                        "Проверьте BANKROT_REFRESH_TOKEN/BANKROT_API_TOKEN в .env "
                        "(refresh-токен мог истечь).",
                        status_code=resp.status_code,
                    )

                # 404 — ресурс не найден (не ретраим)
                if resp.status_code == 404:
                    raise BankrotAPIError(
                        f"Not found: {method} {path}",
                        status_code=404,
                    )

                # Ошибки контракта/доступа не исправятся повтором того же запроса.
                if 400 <= resp.status_code < 500 and resp.status_code != 429:
                    response_text = resp.text[:500] if resp.text else ""
                    raise BankrotAPIError(
                        f"Client error HTTP {resp.status_code} for {method} {path}"
                        + (f": {response_text}" if response_text else ""),
                        status_code=resp.status_code,
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

    @staticmethod
    def _merge_filters(
        defaults: Dict[str, Any], filters: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        merged = deepcopy(defaults)
        if not filters:
            return merged

        for key, value in filters.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value
        return merged

    def get_cases_page(
        self,
        offset: int = 0,
        count: int = 20,
        filters: Optional[Dict[str, Any]] = None,
        sort_order: int = 1,
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
            "filters": self._merge_filters(_DEFAULT_CASE_FILTERS, filters),
        }

        return self._request("POST", "/cases", json=payload)

    def iter_all_cases(
        self,
        page_size: int = 20,
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

    @staticmethod
    def _collection_info(data: Any) -> Tuple[Optional[str], Optional[list], int]:
        if not isinstance(data, dict):
            return None, None, 0

        collection_keys = _COLLECTION_KEYS + tuple(
            key
            for key, value in data.items()
            if isinstance(value, list) and key not in _COLLECTION_KEYS
        )
        for key in collection_keys:
            value = data.get(key)
            if isinstance(value, list):
                total = data.get("totalCount")
                if total is None:
                    total = data.get("count")
                try:
                    total_int = int(total) if total is not None else 0
                except (TypeError, ValueError):
                    total_int = 0
                return key, value, total_int
        return None, None, 0

    def get_case_dataset(
        self,
        case_id: int,
        spec: BankrotCaseDatasetSpec,
        *,
        page_size: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> Any:
        """Загрузить публичный дочерний раздел дела целиком."""
        path = spec.path.format(case_id=case_id)
        if spec.method == "GET":
            return self._request("GET", path)

        if spec.payload_mode == "filters":
            return self._request("POST", path, json={"filters": {}})

        page_size = page_size or settings.BANKROT_RELATED_PAGE_SIZE
        max_pages = max_pages or settings.BANKROT_RELATED_MAX_PAGES
        offset = 0
        merged: Any = None
        merged_key: Optional[str] = None
        previous_page: Optional[list] = None

        for page_number in range(1, max_pages + 1):
            payload = {
                "pagination": {"offset": offset, "count": page_size},
                "sort": {"sortOrder": 1},
                "filters": {},
            }
            page = self._request("POST", path, json=payload)
            collection_key, items, total = self._collection_info(page)

            if merged is None:
                merged = deepcopy(page)
                merged_key = collection_key
            elif collection_key and collection_key == merged_key and items is not None:
                merged[collection_key].extend(items)

            if items is None:
                return page
            if not items:
                break
            if previous_page == items:
                logger.warning(
                    "Bankrot: %s ignored pagination for case_id=%d; stopping at page %d",
                    spec.name,
                    case_id,
                    page_number,
                )
                break

            offset += len(items)
            previous_page = items
            if (total and offset >= total) or len(items) < page_size:
                break
        else:
            raise BankrotAPIError(
                f"Dataset {spec.name} exceeded {max_pages} pages for case_id={case_id}"
            )

        return merged

    def get_debtor_publications(
        self,
        debtor_id: int,
        debtor_name: str,
        *,
        page_size: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> Any:
        """POST /messages — публичные сообщения, найденные по имени должника."""
        page_size = page_size or settings.BANKROT_RELATED_PAGE_SIZE
        max_pages = max_pages or settings.BANKROT_RELATED_MAX_PAGES
        offset = 0
        merged: Any = None
        previous_page: Optional[list] = None

        for page_number in range(1, max_pages + 1):
            filters = self._merge_filters(
                _DEFAULT_PUBLICATION_FILTERS, {"debtor": debtor_name}
            )
            payload = {
                "pagination": {"offset": offset, "count": page_size},
                "sort": {"sortOrder": 1},
                "filters": filters,
            }
            page = self._request("POST", "/messages", json=payload)
            collection_key, items, total = self._collection_info(page)

            if merged is None:
                merged = deepcopy(page)
            elif collection_key and items is not None:
                merged[collection_key].extend(items)

            if items is None:
                return page
            if not items:
                break
            if previous_page == items:
                logger.warning(
                    "Bankrot: publications ignored pagination for debtor_id=%d; "
                    "stopping at page %d",
                    debtor_id,
                    page_number,
                )
                break

            offset += len(items)
            previous_page = items
            if (total and offset >= total) or len(items) < page_size:
                break
        else:
            raise BankrotAPIError(
                f"Publications exceeded {max_pages} pages for debtor_id={debtor_id}"
            )

        return merged

    def _get_entity_related_data(
        self,
        specs: Tuple[BankrotCaseDatasetSpec, ...],
        format_values: Dict[str, int],
        *,
        dataset_names: Optional[set[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for spec in specs:
            if dataset_names is not None and spec.name not in dataset_names:
                continue
            endpoint = spec.path.format(**format_values)
            try:
                payload = self._request("GET", endpoint)
                result[spec.name] = {
                    "endpoint": endpoint,
                    "http_method": "GET",
                    "payload": payload,
                    "fetch_error": None,
                }
            except Exception as exc:
                logger.warning("Bankrot: dataset %s error: %s", spec.name, exc)
                result[spec.name] = {
                    "endpoint": endpoint,
                    "http_method": "GET",
                    "payload": None,
                    "fetch_error": str(exc),
                }
        return result

    def get_manager_related_data(
        self,
        manager_id: int,
        *,
        dataset_names: Optional[set[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Загрузить все публичные разделы карточки управляющего."""
        return self._get_entity_related_data(
            BANKROT_MANAGER_DATASETS,
            {"manager_id": manager_id},
            dataset_names=dataset_names,
        )

    def get_debtor_related_data(
        self,
        debtor_id: int,
        debtor_name: Optional[str] = None,
        *,
        dataset_names: Optional[set[str]] = None,
        page_size: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Загрузить публикации, счета и кошельки должника."""
        result = self._get_entity_related_data(
            BANKROT_DEBTOR_DATASETS,
            {"debtor_id": debtor_id},
            dataset_names=dataset_names,
        )
        if dataset_names is not None and "publications" not in dataset_names:
            return result

        if not debtor_name:
            result["publications"] = {
                "endpoint": "/messages",
                "http_method": "POST",
                "payload": None,
                "fetch_error": "Debtor name is missing; public messages search was skipped",
            }
            return result

        try:
            payload = self.get_debtor_publications(
                debtor_id,
                debtor_name,
                page_size=page_size,
                max_pages=max_pages,
            )
            result["publications"] = {
                "endpoint": "/messages",
                "http_method": "POST",
                "payload": payload,
                "fetch_error": None,
            }
        except Exception as exc:
            logger.warning(
                "Bankrot: dataset publications error debtor_id=%d: %s",
                debtor_id,
                exc,
            )
            result["publications"] = {
                "endpoint": "/messages",
                "http_method": "POST",
                "payload": None,
                "fetch_error": str(exc),
            }
        return result

    def get_case_related_data(
        self,
        case_id: int,
        *,
        dataset_names: Optional[set[str]] = None,
        page_size: Optional[int] = None,
        max_pages: Optional[int] = None,
        delay: float = 0.0,
    ) -> Dict[str, Dict[str, Any]]:
        """Загрузить все поддерживаемые публичные разделы карточки дела."""
        result: Dict[str, Dict[str, Any]] = {}
        for spec in BANKROT_CASE_DATASETS:
            if dataset_names is not None and spec.name not in dataset_names:
                continue

            endpoint = spec.path.format(case_id=case_id)
            try:
                payload = self.get_case_dataset(
                    case_id,
                    spec,
                    page_size=page_size,
                    max_pages=max_pages,
                )
                result[spec.name] = {
                    "endpoint": endpoint,
                    "http_method": spec.method,
                    "payload": payload,
                    "fetch_error": None,
                }
            except Exception as exc:  # один раздел не должен останавливать дело
                logger.warning(
                    "Bankrot: dataset %s error case_id=%d: %s",
                    spec.name,
                    case_id,
                    exc,
                )
                result[spec.name] = {
                    "endpoint": endpoint,
                    "http_method": spec.method,
                    "payload": None,
                    "fetch_error": str(exc),
                }

            if delay > 0:
                time.sleep(delay)

        return result
