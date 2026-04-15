"""
Client for EGR (Egrul) API - uses the same service API.
"""

import logging
from dataclasses import dataclass
from typing import Optional
import asyncio

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
    authority: str = ""
    full_address: str = ""
    postal_code: Optional[int] = None
    region: str = ""
    registration_date: str = ""
    is_empty: bool = True
    
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
        api_url = getattr(settings, "EGR_API_URL", "https://test.tendex.by")
        self.base_url = api_url.rstrip("/")
    
    async def _get(self, path: str) -> dict | None:
        """Make GET request to EGR API."""
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, verify=False) as client:
                headers = {"Accept": "application/json"}
                
                api_key = getattr(settings, "API_KEY", None)
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
    
    async def get_company_profile(self, unp: str) -> Optional[dict]:
        """Get company profile from /api/v1/companies/{unp}."""
        return await self._get(f"/api/v1/companies/{unp}")
    
    async def get_grp_data(self, unp: str) -> Optional[dict]:
        """Get GRP data from /api/v1/grp/{unp}."""
        return await self._get(f"/api/v1/grp/{unp}")
    
    async def get_company_info(self, unp: str) -> EGRCompanyInfo:
        """
        Get normalized company info from EGR API.
        """
        logger.info(f"EGR: requesting data for UNP={unp}")
        
        profile, grp = await asyncio.gather(
            self.get_company_profile(unp),
            self.get_grp_data(unp),
            return_exceptions=True,
        )
        
        if isinstance(profile, Exception):
            logger.error(f"EGR profile error: {profile}")
            profile = None
        if isinstance(grp, Exception):
            logger.error(f"EGR GRP error: {grp}")
            grp = None
            
        profile = profile if isinstance(profile, dict) else {}
        grp = grp if isinstance(grp, dict) else {}
        
        info = EGRCompanyInfo()
        
        # 1. Full name
        if grp.get("full_name"):
            info.full_name = grp["full_name"]
        elif profile.get("current_name_ru"):
            info.full_name = profile["current_name_ru"]
        
        # 2. Short name
        if grp.get("short_name"):
            info.short_name = grp["short_name"]
        elif profile.get("current_short_name_ru"):
            info.short_name = profile["current_short_name_ru"]
        
        # 3. Authority
        if grp.get("inspectorate_name"):
            info.authority = grp["inspectorate_name"]
        
        # 4. Address
        addresses = profile.get("addresses", [])
        if isinstance(addresses, list) and len(addresses) > 0:
            addr = addresses[0]
            if isinstance(addr, dict):
                info.full_address = addr.get("full_address", "")
                info.postal_code = addr.get("postal_code")
                info.region = addr.get("region", "")
        
        if not info.full_address and grp.get("address"):
            info.full_address = grp["address"]
        
        # 5. Registration date
        if grp.get("registration_date"):
            info.registration_date = grp["registration_date"]
        elif profile.get("registration_date"):
            info.registration_date = profile["registration_date"]

        # 6. Contacts (Берем самые свежие с конца)
        contacts = profile.get("contacts", [])
        if isinstance(contacts, list):
            for contact in reversed(contacts):
                if isinstance(contact, dict):
                    if not info.phone and contact.get("phone"):
                        info.phone = contact["phone"]
                    if not info.email and contact.get("email"):
                        info.email = contact["email"]
                    if not info.website and contact.get("website"):
                        info.website = contact["website"]

        # 7. VED (ОКЭД)
        ved_list = profile.get("ved", [])
        if isinstance(ved_list, list):
            for v in reversed(ved_list):
                if isinstance(v, dict) and v.get("ved_code"):
                    info.ved_code = str(v["ved_code"])
                    info.ved_name = str(v.get("ved_name", ""))
                    break
        
        # Flag
        info.is_empty = not any([
            info.full_name, info.short_name, info.authority,
            info.full_address, info.registration_date,
        ])
        
        logger.info(
            f"EGR: UNP={unp} → "
            f"full_name='{info.full_name}', "
            f"short_name='{info.short_name}', "
            f"is_empty={info.is_empty}"
        )
        
        return info
