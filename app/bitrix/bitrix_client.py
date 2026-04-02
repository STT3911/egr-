"""
Bitrix24 API client for managing requisites.
Refactored version.
"""

import logging
from datetime import datetime, timedelta, timezone
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
    
    # Добавлен параметр domain для поддержки мультипортальности в будущем
    def __init__(self, db: AsyncSession, domain: Optional[str] = None):
        self.db = db
        self.domain = domain
        self.app_settings: Optional[AppSettings] = None
    
    async def _load_settings(self) -> AppSettings:
        """Load app settings from database."""
        if self.app_settings:
            return self.app_settings
        
        stmt = select(AppSettings)
        if self.domain:
            stmt = stmt.where(AppSettings.bitrix_domain == self.domain)
        else:
            # Fallback для локального приложения (берем первую запись)
            stmt = stmt.limit(1)
            
        result = await self.db.execute(stmt)
        self.app_settings = result.scalar_one_or_none()
        
        if not self.app_settings:
            raise BitrixAPIError("Bitrix24 app settings not found in database")
        return self.app_settings
    
    async def _refresh_token_if_needed(self, cfg: AppSettings) -> str:
        """Refresh access token if expired or missing."""
        if not cfg.access_token:
            raise BitrixAPIError("Access token not available")
        
        now = datetime.now(timezone.utc)
        
        # Убедимся, что время из БД имеет таймзону (если алхимия возвращает naive datetime)
        expires_at = cfg.token_expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        buffer = timedelta(minutes=5)
        
        if expires_at and (now + buffer > expires_at):
            logger.info("Access token expired, refreshing...")
            
            if not cfg.refresh_token:
                raise BitrixAPIError("Refresh token not available")
            
            async with httpx.AsyncClient(timeout=30) as client:
                # OAuth запрос лучше делать POST-ом, передавая данные в form-data или json
                resp = await client.post(
                    "https://oauth.bitrix.info/oauth/token/",
                    data={
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
                cfg.token_expires_at = now + timedelta(seconds=data.get("expires_in", 3600))
                
                # Внимание: commit сохранит все текущие изменения в сессии.
                await self.db.commit()
                logger.info("Token refreshed successfully")
        
        return cfg.access_token
    
    async def call(self, method: str, params: dict = None) -> Any:
        """
        Make POST API call to Bitrix24 REST API.
        """
        cfg = await self._load_settings()
        
        if not cfg.bitrix_domain:
            raise BitrixAPIError("Bitrix24 domain not configured")
        
        token = await self._refresh_token_if_needed(cfg)
        url = f"https://{cfg.bitrix_domain}/rest/{method}.json"
        
        payload = params or {}
        payload["auth"] = token
        
        # КРИТИЧЕСКОЕ ИЗМЕНЕНИЕ: Используем POST и json=payload. 
        # GET не поддерживает передачу вложенных словарей (например, fields)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload)
            
            if resp.status_code != 200:
                raise BitrixAPIError(f"HTTP {resp.status_code}: {resp.text}")
            
            data = resp.json()
            
            if data.get("error"):
                error = data["error"]
                error_description = data.get("error_description", error)
                raise BitrixAPIError(f"Bitrix API error: {error} - {error_description}")
            
            return data.get("result")
    

    async def get_company(self, company_id: int) -> Optional[dict]:
        try:
            return await self.call("crm.company.get", {"id": company_id})
        except BitrixAPIError as e:
            logger.error(f"Error getting company {company_id}: {e}")
            return None

    async def find_requisite_by_unp(self, company_id: int, unp: str) -> Optional[dict]:
        """Find requisite by UNP."""
        try:
            result = await self.call(
                "crm.requisite.list",
                {
                    "filter": {
                        "ENTITY_TYPE_ID": 4, # Обязательный параметр для ускорения поиска!
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
    
    async def create_requisite(self, entity_id: int, preset_id: int, unp: str, fields: dict) -> int:
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
            await self.call("crm.requisite.update", {"id": requisite_id, "fields": fields})
            return True
        except BitrixAPIError as e:
            logger.error(f"Error updating requisite {requisite_id}: {e}")
            return False

    async def update_requisite_address(self, requisite_id: int, address_type_id: int, address_fields: dict) -> bool:
        """
        Update requisite address directly via crm.requisite.update
        """
        try:
            # В Битрикс24 адреса реквизитов обновляются через передачу массива RQ_ADDR
            # Ключ массива — это ID типа адреса (1 - Юридический, 6 - Фактический и т.д.)
            await self.call(
                "crm.requisite.update",
                {
                    "id": requisite_id,
                    "fields": {
                        "RQ_ADDR": {
                            str(address_type_id): address_fields
                        }
                    }
                },
            )
            return True
        except BitrixAPIError as e:
            logger.error(f"Error updating address for requisite {requisite_id}: {e}")
            return False

    async def get_requisite_presets(self) -> list:
        """Получение списка пресетов реквизитов."""
        result = await self.call("crm.requisite.preset.list ", {
            "select": ["ID", "NAME"],
            "filter": {"ENTITY_TYPE_ID": 8}, # 8 = Requisites
            "order": {"SORT": "ASC"}
        })
        return result if isinstance(result, list) else []

    async def get_company_userfields(self) -> list:
        """Получение списка полей компании."""
        result = await self.call("crm.userfield.list", {
            "filter": {"ENTITY_ID": "CRM_COMPANY"}
        })
        return result if isinstance(result, list) else []

    async def create_unp_userfield(self) -> dict:
        """Автоматическое создание поля 'УНП (EGR)' в компаниях."""
        field_data = {
            "USER_TYPE_ID": "string",
            "ENTITY_ID": "CRM_COMPANY",
            "FIELD_NAME": "EGR_UNP",
            "EDIT_FORM_LABEL": "УНП (EGR)",
            "LIST_COLUMN_LABEL": "УНП (EGR)",
            "USER_TYPE_ID": "string",
            "XML_ID": "EGR_UNP"
        }
        field_id = await self.call("crm.userfield.add", {"fields": field_data})
        return {"ID": field_id, "FIELD_NAME": "UF_CRM_EGR_UNP"} 