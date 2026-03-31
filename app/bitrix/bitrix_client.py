"""
Bitrix24 API client for managing requisites.
"""

import logging
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bitrix.models import AppSettings
from app.core.config import settings

logger = logging.getLogger(__name__)


class BitrixAPIError(Exception):
    """Bitrix24 API error."""
    pass


class BitrixClient:
    """
    Async client for Bitrix24 REST API.
    Handles OAuth token management and API calls.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.app_settings: Optional[AppSettings] = None
    
    async def _load_settings(self) -> AppSettings:
        """Load app settings from database."""
        if self.app_settings:
            return self.app_settings
        result = await self.db.execute(select(AppSettings).where(AppSettings.id == 1))
        self.app_settings = result.scalar_one_or_none()
        if not self.app_settings:
            raise BitrixAPIError("Bitrix24 app settings not found")
        return self.app_settings
    
    async def _refresh_token_if_needed(self, cfg: AppSettings) -> str:
        """Refresh access token if expired or missing."""
        import datetime
        
        if not cfg.access_token:
            raise BitrixAPIError("Access token not available")
        
        # Check if token is expired (with 5 minute buffer)
        if cfg.token_expires_at:
            buffer = datetime.timedelta(minutes=5)
            if datetime.datetime.utcnow() + buffer > cfg.token_expires_at:
                logger.info("Access token expired, refreshing...")
                
                if not cfg.refresh_token:
                    raise BitrixAPIError("Refresh token not available")
                
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(
                        "https://oauth.bitrix.info/oauth/token/",
                        params={
                            "grant_type": "refresh_token",
                            "client_id": settings.BITRIX_CLIENT_ID,
                            "client_secret": settings.BITRIX_CLIENT_SECRET,
                            "refresh_token": cfg.refresh_token,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    
                    cfg.access_token = data.get("access_token", cfg.access_token)
                    cfg.refresh_token = data.get("refresh_token", cfg.refresh_token)
                    cfg.token_expires_at = datetime.datetime.utcnow() + datetime.timedelta(
                        seconds=data.get("expires_in", 3600)
                    )
                    await self.db.commit()
                    logger.info("Token refreshed successfully")
        
        return cfg.access_token
    
    async def call(self, method: str, params: dict = None) -> Any:
        """
        Make API call to Bitrix24 REST API.
        
        Args:
            method: Bitrix24 method name (e.g., "crm.requisite.list")
            params: Method parameters
            
        Returns:
            API response data
        """
        cfg = await self._load_settings()
        
        if not cfg.bitrix_domain:
            raise BitrixAPIError("Bitrix24 domain not configured")
        
        token = await self._refresh_token_if_needed(cfg)
        url = f"https://{cfg.bitrix_domain}/rest/{method}.json"
        
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                url,
                params={"auth": token, **(params or {})},
            )
            
            if resp.status_code != 200:
                raise BitrixAPIError(f"HTTP {resp.status_code}: {resp.text}")
            
            data = resp.json()
            
            if data.get("error"):
                error = data["error"]
                error_description = data.get("error_description", error)
                raise BitrixAPIError(f"Bitrix API error: {error} - {error_description}")
            
            return data.get("result")
    
    async def get_company(self, company_id: int) -> Optional[dict]:
        """Get company by ID."""
        try:
            result = await self.call("crm.company.get", {"id": company_id})
            return result
        except BitrixAPIError as e:
            logger.error(f"Error getting company {company_id}: {e}")
            return None
    
    async def is_admin(self) -> bool:
        """Check if current user is admin."""
        try:
            result = await self.call("user.admin")
            return bool(result)
        except BitrixAPIError:
            return False
    
    async def get_current_user(self) -> Optional[dict]:
        """Get current user info."""
        try:
            result = await self.call("user.current")
            return result
        except BitrixAPIError:
            return None
    
    async def get_requisite_presets(self) -> list[dict]:
        """Get list of requisite presets."""
        try:
            result = await self.call("crm.requisite.preset.list", {})
            presets = result or []
            return [p["preset"] for p in presets]
        except BitrixAPIError as e:
            logger.error(f"Error getting presets: {e}")
            return []
    
    async def get_company_userfields(self) -> list[dict]:
        """Get company user fields."""
        try:
            result = await self.call("crm.company.userfield.list", {})
            fields = result or []
            return fields
        except BitrixAPIError as e:
            logger.error(f"Error getting user fields: {e}")
            return []
    
    async def find_requisite_by_unp(self, company_id: int, unp: str) -> Optional[dict]:
        """Find requisite by UNP."""
        try:
            result = await self.call(
                "crm.requisite.list",
                {
                    "filter": {
                        "ENTITY_ID": company_id,
                        "RQ_INN": unp,
                    },
                    "select": ["ID", "ENTITY_ID", "RQ_NAME", "RQ_SHORT_NAME", "RQ_LEGAL_FORM", "RQ_REASON"],
                },
            )
            requisites = result or []
            return requisites[0] if requisites else None
        except BitrixAPIError as e:
            logger.error(f"Error finding requisite: {e}")
            return None
    
    async def create_requisite(
        self,
        entity_id: int,
        preset_id: int,
        unp: str,
        fields: dict,
    ) -> int:
        """Create new requisite."""
        data = {
            "fields": {
                "ENTITY_TYPE_ID": 4,  # Company
                "ENTITY_ID": entity_id,
                "PRESET_ID": preset_id,
                "RQ_INN": unp,
                **fields,
            }
        }
        result = await self.call("crm.requisite.add", data)
        return int(result)
    
    async def update_requisite(self, requisite_id: int, fields: dict) -> bool:
        """Update requisite fields."""
        try:
            await self.call(
                "crm.requisite.update",
                {"id": requisite_id, "fields": fields},
            )
            return True
        except BitrixAPIError as e:
            logger.error(f"Error updating requisite {requisite_id}: {e}")
            return False
    
    async def get_address_type_id(self, type_name: str = "LEGAL") -> int:
        """Get address type ID by name."""
        try:
            result = await self.call("crm.enum.addresstype", {})
            types = result or []
            for addr_type in types:
                if addr_type.get("NAME", "").upper() == type_name.upper():
                    return int(addr_type["ID"])
            # Default to LEGAL (1)
            return 1
        except BitrixAPIError:
            return 1
    
    async def update_requisite_address(
        self,
        requisite_id: int,
        address_type_id: int,
        address_fields: dict,
    ) -> bool:
        """Update requisite address."""
        try:
            await self.call(
                "crm.requisite.address.update",
                {
                    "requisiteId": requisite_id,
                    "typeId": address_type_id,
                    **address_fields,
                },
            )
            return True
        except BitrixAPIError as e:
            logger.error(f"Error updating address for requisite {requisite_id}: {e}")
            return False
