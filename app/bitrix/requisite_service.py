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


def _apply_ip_mask(mask: str, company_name: str, unp: str, fallback: str) -> str:
    """Безопасное применение маски из БД."""
    if not mask:
        mask = fallback
    try:
        return mask.format(company_name=company_name, company_unp=unp)
    except KeyError:
        # Если админ ошибся в переменных в админке
        return fallback.format(company_name=company_name, company_unp=unp)


class RequisiteService:
    """
    Service for auto-filling company requisites.
    Uses EGR API data and applies IP masks from DB.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.bitrix = BitrixClient(db)
        self.egr = EGRClient()
    
    async def process_company_update(self, company_id: int) -> None:
        logger.info(f"[Company {company_id}] Starting processing")
        
        # Шаг 1: Загружаем настройки из БД (ВКЛЮЧАЯ МАСКИ)
        result = await self.db.execute(select(AppSettings).limit(1))
        app_cfg = result.scalar_one_or_none()
        
        if not app_cfg or not app_cfg.requisite_preset_id or not app_cfg.unp_field_code:
            logger.warning(f"[Company {company_id}] App settings are incomplete - skipping")
            return
            
        # Шаг 2: Получаем компанию из CRM
        try:
            company = await self.bitrix.get_company(company_id)
        except BitrixAPIError as e:
            logger.error(f"[Company {company_id}] get_company error: {e}")
            return
            
        if not company:
            return
            
        company_title = company.get("TITLE", "")
        
        # Шаг 3: Читаем УНП
        unp_raw = company.get(app_cfg.unp_field_code, "")
        if not unp_raw:
            logger.info(f"[Company {company_id}] UNP is empty - skipping")
            return
            
        unp = str(unp_raw).strip()
        
        # Шаг 4: СРАЗУ идем в ЕГР за эталонными данными
        egr_info = await self.egr.get_company_info(unp)
        
        # Шаг 5: Формируем правильные поля для записи
        is_ip = egr_info.is_empty or "ИП" in company_title.upper() or "ИНДИВИДУАЛЬНЫЙ" in company_title.upper()
        fields_to_write = {}
        
        if is_ip:
            name = _apply_ip_mask(app_cfg.ip_mask_short, company_title, unp, "ИП {company_name}")
            fields_to_write["NAME"] = name
            fields_to_write["RQ_COMPANY_NAME"] = name
            fields_to_write["RQ_COMPANY_FULL_NAME"] = _apply_ip_mask(
                app_cfg.ip_mask_full, company_title, unp, "Индивидуальный предприниматель {company_name}"
            )
            fields_to_write["RQ_LEGAL_FORM"] = _apply_ip_mask(
                app_cfg.ip_mask_basis, company_title, unp, "Свидетельство о регистрации № {company_unp}"
            )
        else:
            name = egr_info.short_name or egr_info.full_name
            fields_to_write["NAME"] = name
            fields_to_write["RQ_COMPANY_NAME"] = egr_info.short_name
            fields_to_write["RQ_COMPANY_FULL_NAME"] = egr_info.full_name
            if egr_info.authority:
                fields_to_write["RQ_LEGAL_FORM"] = egr_info.authority
                
        # Добавляем адрес
        if egr_info.full_address:
            address_fields = {"ADDRESS_1": egr_info.full_address}
            if egr_info.postal_code:
                address_fields["ZIP_CODE"] = str(egr_info.postal_code)
            if egr_info.region:
                address_fields["REGION"] = egr_info.region
            fields_to_write["RQ_ADDR"] = {"1": address_fields}

        if not fields_to_write.get("NAME"):
            logger.info(f"[Company {company_id}] No data from EGR to write")
            return

        # Шаг 6: Получаем то, что СЕЙЧАС написано в Битриксе
        try:
            requisite = await self.bitrix.find_requisite_by_unp(company_id, unp)
        except BitrixAPIError as e:
            logger.error(f"[Company {company_id}] Error finding requisite: {e}")
            return
            
        is_new = requisite is None
        new_title = fields_to_write.get("RQ_COMPANY_NAME") or fields_to_write.get("NAME")

        # --- Шаг 7: УМНАЯ ЗАЩИТА ОТ ЦИКЛА (Сравнение) ---
        needs_title_update = bool(new_title and company_title != new_title)
        
        needs_req_update = False
        if is_new:
            needs_req_update = True
        else:
            existing_name = requisite.get("NAME", "")
            if existing_name != fields_to_write.get("NAME"):
                needs_req_update = True

        needs_address_update = False
        needs_contact_update = False  # НОВАЯ ПЕРЕМЕННАЯ ДЛЯ КОНТАКТОВ

        try:
            current_comp = await self.bitrix.call("crm.company.get", {"id": company_id})
            
            # 1. Проверяем Адрес
            if egr_info.full_address and current_comp.get("ADDRESS") != egr_info.full_address:
                needs_address_update = True
                
            # 2. Проверяем Телефон (если есть в ЕГР, но пуст в Битриксе)
            if hasattr(egr_info, 'phone') and egr_info.phone:
                if not current_comp.get("PHONE"):
                    needs_contact_update = True
                    
            # 3. Проверяем E-mail (если есть в ЕГР, но пуст в Битриксе)
            if hasattr(egr_info, 'email') and egr_info.email:
                if not current_comp.get("EMAIL"):
                    needs_contact_update = True
                    
            # 4. Проверяем Сайт (если есть в ЕГР, но пуст в Битриксе)
            if hasattr(egr_info, 'website') and egr_info.website:
                if not current_comp.get("WEB"):
                    needs_contact_update = True

        except Exception as e:
            logger.error(f"[Company {company_id}] Error checking current fields: {e}")

        # Теперь защита останавливает скрипт ТОЛЬКО если ВСЕ поля идеальны
        if not needs_title_update and not needs_req_update and not needs_address_update and not needs_contact_update:
            logger.info(f"[Company {company_id}] Битрикс и ЕГР синхронизированы. Останавливаемся (защита от цикла).")
            return
        # ------------------------------------------------

        # Шаг 8: Обновляем Битрикс!
        try:
            # 1. Формируем поля для обновления фасада карточки
            company_update_fields = {}
            if needs_title_update:
                company_update_fields["TITLE"] = new_title
                
            if needs_address_update:
                company_update_fields["ADDRESS"] = egr_info.full_address
                if egr_info.postal_code:
                    company_update_fields["ADDRESS_POSTAL_CODE"] = str(egr_info.postal_code)

            # --- ЗАПОЛНЯЕМ КОНТАКТЫ ---
            if hasattr(egr_info, 'phone') and egr_info.phone:
                company_update_fields["PHONE"] = [{"VALUE": egr_info.phone, "VALUE_TYPE": "WORK"}]
                
            if hasattr(egr_info, 'email') and egr_info.email:
                company_update_fields["EMAIL"] = [{"VALUE": egr_info.email, "VALUE_TYPE": "WORK"}]
                
            if hasattr(egr_info, 'website') and egr_info.website:
                company_update_fields["WEB"] = [{"VALUE": egr_info.website, "VALUE_TYPE": "WORK"}]
            # ----------------------------------------

            # Если есть что обновлять - отправляем запрос
            if company_update_fields:
                await self.bitrix.call("crm.company.update", {
                    "id": company_id,
                    "fields": company_update_fields
                })
                logger.info(f"[Company {company_id}] Updated main card fields: {list(company_update_fields.keys())}")

            # 2. Обновляем реквизиты (бухгалтерию)
            if needs_req_update:
                if is_new:
                    requisite_id = await self.bitrix.create_requisite(
                        entity_id=company_id,
                        preset_id=app_cfg.requisite_preset_id,
                        unp=unp,
                        fields=fields_to_write,
                    )
                    logger.info(f"[Company {company_id}] Created new requisite ID={requisite_id}")
                else:
                    requisite_id = int(requisite["ID"])
                    await self.bitrix.update_requisite(requisite_id, unp, fields_to_write)
                    logger.info(f"[Company {company_id}] Overwrote existing requisite ID={requisite_id}")
                    
        except BitrixAPIError as e:
            logger.error(f"[Company {company_id}] Error saving data: {e}")

        logger.info(f"[Company {company_id}] Processing completed successfully")