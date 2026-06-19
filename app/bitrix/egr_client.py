"""
Client for EGR (Egrul) API - uses the same service API.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 20


@dataclass
class EGRAddress:
    """Address data."""
    full_address: str = ""
    postal_code: Optional[int] = None
    region: str = ""


@dataclass
class EGRName:
    """Name data."""
    full_name_ru: str = ""
    short_name_ru: str = ""


@dataclass
class EGRCompanyInfo:
    """Normalized company data from EGR."""
    full_name: str = ""
    short_name: str = ""
    director: str = ""
    authority: str = ""
    full_address: str = ""
    postal_code: Optional[int] = None
    region: str = ""
    registration_date: str = ""
    is_empty: bool = True

    # Тип плательщика, вычисленный на стороне сервиса (None — не определён).
    is_ip: Optional[bool] = None

    # Контакты и деятельность
    phone: str = ""
    email: str = ""
    website: str = ""
    ved_code: str = ""
    ved_name: str = ""


class EGRClient:
    """
    Client for EGR API (test.tendex.by).
    Uses the same endpoints as the frontend.
    """
    
    def __init__(self):
        # Источник данных — наш сервис (test.tendex.by), а НЕ upstream egr.gov.by.
        api_url = getattr(settings, "TENDEX_API_URL", None) or "https://test.tendex.by"
        self.base_url = api_url.rstrip("/")
    
    async def _get(self, path: str) -> dict | None:
        """Make GET request to EGR API."""
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, verify=False) as client:
                headers = {"Accept": "application/json"}

                api_key = getattr(settings, "TENDEX_API_KEY", None) or getattr(settings, "API_KEY", None)
                if api_key:
                    headers["X-API-Key"] = api_key
                    
                resp = await client.get(url, headers=headers)
                
                if resp.status_code == 404:
                    logger.info(f"EGR: UNP not found ({url})")
                    return None
                
                if resp.status_code != 200:
                    logger.warning(f"EGR: status {resp.status_code} for {url}")
                    return None
                
                try:
                    return resp.json()
                except ValueError:
                    logger.error(f"EGR: invalid JSON response from {url}")
                    return None
                    
        except httpx.TimeoutException:
            logger.error(f"EGR: timeout - {url}")
        except httpx.RequestError as e:
            logger.error(f"EGR: network error - {url}: {e}")
        except Exception as e:
            logger.error(f"EGR: unexpected error - {url}: {e}")
            
        return None
    
    async def get_requisite_data(self, unp: str) -> Optional[dict]:
        """Get the thin requisite slice from /api/v1/bitrix/requisite/{unp}."""
        return await self._get(f"/api/v1/bitrix/requisite/{unp}")

    async def get_company_info(self, unp: str) -> EGRCompanyInfo:
        """
        Получить данные компании под реквизит через ТОНКИЙ эндпоинт сервиса.
        Эндпоинт отдаёт только нужные поля и уже вычисленный is_ip.
        """
        logger.info(f"EGR: requesting requisite data for UNP={unp}")

        data = await self.get_requisite_data(unp)
        if not isinstance(data, dict):
            return EGRCompanyInfo()  # is_empty=True по умолчанию

        info = EGRCompanyInfo()
        info.full_name = data.get("full_name") or ""
        info.short_name = data.get("short_name") or ""
        info.director = data.get("director") or ""
        info.authority = data.get("authority") or ""
        info.registration_date = data.get("registration_date") or ""
        info.ved_code = str(data.get("okved") or "")
        info.is_ip = data.get("is_ip")

        info.phone = data.get("phone") or ""
        info.email = data.get("email") or ""
        info.website = data.get("website") or ""

        address = data.get("address")
        if isinstance(address, dict):
            info.full_address = address.get("full_address") or ""
            info.postal_code = address.get("postal_code")
            info.region = address.get("region") or ""

        info.is_empty = not any([
            info.full_name, info.short_name, info.authority,
            info.full_address, info.registration_date,
        ])

        logger.info(
            f"EGR: UNP={unp} → full_name='{info.full_name}', "
            f"is_ip={info.is_ip}, is_empty={info.is_empty}"
        )
        return info
