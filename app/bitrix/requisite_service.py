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
        
        # Шаг 4: Ищем существующий реквизит
        try:
            requisite = await self.bitrix.find_requisite_by_unp(company_id, unp)
        except BitrixAPIError as e:
            logger.error(f"[Company {company_id}] Error finding requisite: {e}")
            return
            
        # Защита от бесконечного цикла: проверяем, нужно ли вообще что-то обновлять
        is_new = requisite is None
        if not is_new:
            rq_name = (requisite.get("RQ_NAME") or "").strip()
            rq_short_name = (requisite.get("RQ_SHORT_NAME") or "").strip()
            rq_basis = (requisite.get("RQ_LEGAL_FORM") or "").strip() # В зависимости от вашего пресета
            
            # Если основные поля уже заполнены — прерываем работу.
            if rq_name and rq_short_name and rq_basis:
                logger.info(f"[Requisite {requisite.get('ID')}] Fields already filled - skipping to prevent loop")
                return

        # Шаг 5: Идем в ЕГР (Только если реквизит новый или пустой!)
        egr_info = await self.egr.get_company_info(unp)
        
        # Шаг 6: Формируем данные для заполнения (Используем маски из БД!)
        # Простейшая эвристика: если ЕГР вернул пустоту, или в названии есть "ИП", считаем это ИП.
        # В идеале egr_info должен возвращать флаг is_ip
        is_ip = egr_info.is_empty or "ИП" in company_title.upper() or "ИНДИВИДУАЛЬНЫЙ" in company_title.upper()
        
        fields_to_write = {}
        
        if is_ip:
            # ПРИМЕНЯЕМ НАСТРОЙКИ АДМИНА
            fields_to_write["RQ_NAME"] = _apply_ip_mask(
                app_cfg.ip_mask_full, company_title, unp, "Индивидуальный предприниматель {company_name}"
            )
            fields_to_write["RQ_SHORT_NAME"] = _apply_ip_mask(
                app_cfg.ip_mask_short, company_title, unp, "ИП {company_name}"
            )
            # Часто основание пишется в RQ_DIRECTOR, но оставляю вашу логику
            fields_to_write["RQ_LEGAL_FORM"] = _apply_ip_mask(
                app_cfg.ip_mask_basis, company_title, unp, "Свидетельство о регистрации № {company_unp}"
            )
        else:
            # Это юридическое лицо (ООО, ЗАО и т.д.)
            if egr_info.full_name:
                fields_to_write["RQ_NAME"] = egr_info.full_name
            if egr_info.short_name:
                fields_to_write["RQ_SHORT_NAME"] = egr_info.short_name
            if egr_info.authority:
                fields_to_write["RQ_LEGAL_FORM"] = egr_info.authority
                
        # Шаг 7: Добавляем юридический адрес В ТОТ ЖЕ ЗАПРОС
        if egr_info.full_address:
            address_fields = {"ADDRESS_1": egr_info.full_address}
            if egr_info.postal_code:
                address_fields["ZIP_CODE"] = str(egr_info.postal_code)
            if egr_info.region:
                address_fields["REGION"] = egr_info.region
                
            # Тип адреса 1 - это Юридический по умолчанию в Битрикс24
            fields_to_write["RQ_ADDR"] = {"1": address_fields}
            
        if not fields_to_write:
            logger.info(f"[Company {company_id}] No data to write")
            return

        # Шаг 8: Делаем ОДИН запрос к API Битрикс24 (Создание или Обновление)
        try:
            if is_new:
                requisite_id = await self.bitrix.create_requisite(
                    entity_id=company_id,
                    preset_id=app_cfg.requisite_preset_id,
                    unp=unp,
                    fields=fields_to_write,
                )
                logger.info(f"[Company {company_id}] Created new requisite ID={requisite_id} with data")
            else:
                requisite_id = int(requisite["ID"])
                # ИСПРАВЛЕНО: добавили unp вторым аргументом
                await self.bitrix.update_requisite(requisite_id, unp, fields_to_write) 
                logger.info(f"[Company {company_id}] Updated existing requisite ID={requisite_id} with data")
                
        except BitrixAPIError as e:
            logger.error(f"[Company {company_id}] Error saving requisite: {e}")