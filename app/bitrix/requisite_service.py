"""
Service for processing company requisites.
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.bitrix.models import AppSettings
from app.bitrix.bitrix_client import BitrixClient, BitrixAPIError
from app.bitrix.egr_client import EGRClient

logger = logging.getLogger(__name__)


def _fallback_full_name(company_title: str) -> str:
    """Mask for full name of IP (Individual Entrepreneur)."""
    return f"Индивидуальный предприниматель {company_title}"


def _fallback_short_name(company_title: str) -> str:
    """Mask for short name of IP."""
    return f"ИП {company_title}"


def _fallback_authority(unp: str) -> str:
    """Mask for authority document of IP."""
    return f"свидетельства о регистрации № {unp}"


class RequisiteService:
    """
    Service for auto-filling company requisites.
    Uses EGR API data.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.bitrix = BitrixClient(db)
        self.egr = EGRClient()
    
    async def process_company_update(self, company_id: int) -> None:
        """
        Main handler for OnCrmCompanyUpdate event.
        
        Steps:
        1. Load app settings from DB
        2. Get company data from CRM
        3. Read UNP from user field
        4. Find or create requisite
        5. Check which fields are empty
        6. Request data from EGR
        7. Fill only empty fields
        8. Update legal address
        """
        logger.info(f"[Company {company_id}] Starting OnCrmCompanyUpdate processing")
        
        # Step 1: Load settings
        result = await self.db.execute(
            select(AppSettings).where(AppSettings.id == 1)
        )
        app_cfg = result.scalar_one_or_none()
        
        if not app_cfg:
            logger.error(f"[Company {company_id}] Settings not found - skipping")
            return
        
        if not app_cfg.requisite_preset_id or not app_cfg.unp_field_code:
            logger.warning(
                f"[Company {company_id}] Preset ({app_cfg.requisite_preset_id}) "
                f"or UNP field ({app_cfg.unp_field_code}) not configured - skipping"
            )
            return
        
        # Step 2: Get company from CRM
        try:
            company = await self.bitrix.get_company(company_id)
        except BitrixAPIError as e:
            logger.error(f"[Company {company_id}] crm.company.get error: {e}")
            return
        
        if not company:
            logger.warning(f"[Company {company_id}] Company not found in CRM")
            return
        
        company_title = company.get("TITLE", "")
        
        # Step 3: Read UNP from user field
        unp_raw = company.get(app_cfg.unp_field_code, "")
        if not unp_raw:
            logger.info(
                f"[Company {company_id}] UNP field '{app_cfg.unp_field_code}' is empty - skipping"
            )
            return
        
        unp = str(unp_raw).strip()
        logger.info(f"[Company {company_id}] UNP='{unp}', title='{company_title}'")
        
        # Step 4: Find or create requisite
        try:
            requisite = await self.bitrix.find_requisite_by_unp(company_id, unp)
        except BitrixAPIError as e:
            logger.error(f"[Company {company_id}] Error finding requisite: {e}")
            return
        
        if requisite:
            requisite_id = int(requisite["ID"])
            logger.info(f"[Company {company_id}] Found requisite ID={requisite_id}")
        else:
            logger.info(f"[Company {company_id}] Requisite not found - creating new")
            try:
                requisite_id = await self.bitrix.create_requisite(
                    entity_id=company_id,
                    preset_id=app_cfg.requisite_preset_id,
                    unp=unp,
                    fields={},
                )
                requisite = {"ID": requisite_id}
                logger.info(f"[Company {company_id}] Created requisite ID={requisite_id}")
            except BitrixAPIError as e:
                logger.error(f"[Company {company_id}] Error creating requisite: {e}")
                return
        
        # Step 5: Check empty fields
        rq_name = (requisite.get("RQ_NAME") or "").strip()
        rq_short_name = (requisite.get("RQ_SHORT_NAME") or "").strip()
        rq_legal_form = (requisite.get("RQ_LEGAL_FORM") or "").strip()
        rq_reason = (requisite.get("RQ_REASON") or "").strip()
        
        need_name = not rq_name
        need_short_name = not rq_short_name
        need_authority = not rq_legal_form and not rq_reason
        
        if not any([need_name, need_short_name, need_authority]):
            logger.info(f"[Requisite {requisite_id}] All fields already filled - skipping")
            return
        
        # Step 6: Get data from EGR
        egr_info = await self.egr.get_company_info(unp)
        
        if egr_info.is_empty:
            logger.warning(
                f"[Requisite {requisite_id}] EGR returned no data for UNP={unp} - "
                f"using IP masks"
            )
        
        # Step 7: Fill empty fields
        fields_to_update = {}
        
        if need_name:
            full_name = egr_info.full_name or _fallback_full_name(company_title)
            fields_to_update["RQ_NAME"] = full_name
            logger.debug(f"[Requisite {requisite_id}] RQ_NAME ← '{full_name}'")
        
        if need_short_name:
            short_name = egr_info.short_name or _fallback_short_name(company_title)
            fields_to_update["RQ_SHORT_NAME"] = short_name
            logger.debug(f"[Requisite {requisite_id}] RQ_SHORT_NAME ← '{short_name}'")
        
        if need_authority:
            authority = egr_info.authority or _fallback_authority(unp)
            fields_to_update["RQ_LEGAL_FORM"] = authority
            logger.debug(f"[Requisite {requisite_id}] RQ_LEGAL_FORM ← '{authority}'")
        
        if fields_to_update:
            logger.info(
                f"[Requisite {requisite_id}] Updating fields: {list(fields_to_update.keys())}"
            )
            try:
                await self.bitrix.update_requisite(requisite_id, fields_to_update)
                logger.info(f"[Requisite {requisite_id}] Fields updated successfully")
            except BitrixAPIError as e:
                logger.error(f"[Requisite {requisite_id}] crm.requisite.update error: {e}")
        
        # Step 8: Update legal address
        if egr_info.full_address:
            logger.info(
                f"[Requisite {requisite_id}] Updating address: '{egr_info.full_address}'"
            )
            try:
                address_type_id = await self.bitrix.get_address_type_id("LEGAL")
                address_fields = {"ADDRESS_1": egr_info.full_address}
                if egr_info.postal_code:
                    address_fields["ZIP_CODE"] = str(egr_info.postal_code)
                if egr_info.region:
                    address_fields["REGION"] = egr_info.region
                
                await self.bitrix.update_requisite_address(
                    requisite_id=requisite_id,
                    address_type_id=address_type_id,
                    address_fields=address_fields,
                )
                logger.info(f"[Requisite {requisite_id}] Address updated")
            except BitrixAPIError as e:
                logger.error(f"[Requisite {requisite_id}] Address update error: {e}")
        
        logger.info(f"[Company {company_id}] Processing completed")
