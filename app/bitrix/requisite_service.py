import logging
from datetime import datetime
from app.bitrix.client import BitrixAPIError # Убедись, что путь к ошибкам у тебя такой

logger = logging.getLogger(__name__)

class RequisiteService:
    def __init__(self, bitrix_client, egr_client):
        self.bitrix = bitrix_client
        self.egr = egr_client

    async def process_company_update(self, company_id: int):
        """Main processing logic for OnCrmCompanyUpdate."""
        logger.info(f"[Company {company_id}] Starting processing")

        try:
            # Шаг 1-3: Получаем компанию и УНП
            company = await self.bitrix.call("crm.company.get", {"id": company_id})
            company_title = company.get("TITLE", "")
            
            # Предполагаем, что твое поле называется UF_CRM_UNP (измени, если у тебя другое, например UF_CRM_...)
            unp_raw = company.get("UF_CRM_UNP")  
            
            if not unp_raw or str(unp_raw).strip() == "":
                logger.info(f"[Company {company_id}] No UNP provided, skipping")
                return
                
            unp = str(unp_raw).strip()

            # Шаг 4: СРАЗУ идем в ЕГР за эталонными данными
            egr_info = await self.egr.get_company_info(unp)
            
            if egr_info.is_empty:
                logger.info(f"[Company {company_id}] No data from EGR to write")
                return

            # Шаг 5: Формируем правильные поля для записи
            is_ip = "ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ" in egr_info.full_name.upper() or "ИП " in egr_info.short_name.upper()
            fields_to_write = {}
            
            if is_ip:
                name = egr_info.short_name or egr_info.full_name
                fields_to_write["NAME"] = name
                fields_to_write["RQ_COMPANY_NAME"] = name
                fields_to_write["RQ_COMPANY_FULL_NAME"] = egr_info.full_name
                fields_to_write["RQ_LEGAL_FORM"] = f"Свидетельство о регистрации № {unp}"
            else:
                name = egr_info.short_name or egr_info.full_name
                fields_to_write["NAME"] = name
                fields_to_write["RQ_COMPANY_NAME"] = egr_info.short_name
                fields_to_write["RQ_COMPANY_FULL_NAME"] = egr_info.full_name
                if egr_info.authority:
                    fields_to_write["RQ_LEGAL_FORM"] = egr_info.authority
                    
            # Добавляем ОКЭД
            if egr_info.ved_code:
                fields_to_write["RQ_OKVED"] = egr_info.ved_code

            # Добавляем Дату регистрации
            if egr_info.registration_date:
                try:
                    dt = datetime.strptime(egr_info.registration_date, "%Y-%m-%d")
                    fields_to_write["RQ_STATE_REG_DATE"] = dt.strftime("%d.%m.%Y")
                except ValueError:
                    pass

            # Добавляем Юридический адрес (Тип 6 в Битриксе)
            if egr_info.full_address:
                address_fields = {"ADDRESS_1": egr_info.full_address}
                if egr_info.postal_code:
                    address_fields["ZIP_CODE"] = str(egr_info.postal_code)
                if egr_info.region:
                    address_fields["REGION"] = egr_info.region
                fields_to_write["RQ_ADDR"] = {"6": address_fields}

            # Шаг 6: Получаем ЛЮБЫЕ старые реквизиты компании
            try:
                req_list = await self.bitrix.call("crm.requisite.list", {
                    "filter": {
                        "ENTITY_ID": company_id, 
                        "ENTITY_TYPE_ID": 4  # 4 - ID сущности "Компания"
                    }
                })
                requisite = req_list[0] if req_list else None
            except BitrixAPIError as e:
                logger.error(f"[Company {company_id}] Error finding requisite: {e}")
                return
                
            is_new = requisite is None
            new_title = fields_to_write.get("RQ_COMPANY_NAME") or fields_to_write.get("NAME")

            # --- Шаг 7: УМНАЯ ЗАЩИТА ОТ ЦИКЛА ---
            needs_title_update = bool(new_title and company_title != new_title)
            
            needs_req_update = False
            if is_new:
                needs_req_update = True
            else:
                existing_name = requisite.get("NAME", "")
                if existing_name != fields_to_write.get("NAME"):
                    needs_req_update = True

            needs_address_update = False
            needs_contact_update = False 

            # Проверяем фасад карточки
            try:
                if egr_info.full_address and company.get("REG_ADDRESS") != egr_info.full_address:
                    needs_address_update = True
                    
                if hasattr(egr_info, 'phone') and egr_info.phone:
                    if not company.get("PHONE"):
                        needs_contact_update = True
                        
                if hasattr(egr_info, 'email') and egr_info.email:
                    if not company.get("EMAIL"):
                        needs_contact_update = True
                        
                if hasattr(egr_info, 'website') and egr_info.website:
                    if not company.get("WEB"):
                        needs_contact_update = True
            except Exception as e:
                logger.error(f"[Company {company_id}] Error checking current fields: {e}")

            if not any([needs_title_update, needs_req_update, needs_address_update, needs_contact_update]):
                logger.info(f"[Company {company_id}] Битрикс и ЕГР синхронизированы. Останавливаемся (защита от цикла).")
                return
            # ------------------------------------------------

            # Шаг 8: Обновляем Битрикс!
            try:
                # 1. Фасад карточки
                company_update_fields = {}
                if needs_title_update:
                    company_update_fields["TITLE"] = new_title
                    
                if needs_address_update:
                    company_update_fields["REG_ADDRESS"] = egr_info.full_address
                    if egr_info.postal_code:
                        company_update_fields["REG_ADDRESS_POSTAL_CODE"] = str(egr_info.postal_code)

                if needs_contact_update:
                    if hasattr(egr_info, 'phone') and egr_info.phone:
                        company_update_fields["PHONE"] = [{"VALUE": egr_info.phone, "VALUE_TYPE": "WORK"}]
                    if hasattr(egr_info, 'email') and egr_info.email:
                        company_update_fields["EMAIL"] = [{"VALUE": egr_info.email, "VALUE_TYPE": "WORK"}]
                    if hasattr(egr_info, 'website') and egr_info.website:
                        company_update_fields["WEB"] = [{"VALUE": egr_info.website, "VALUE_TYPE": "WORK"}]

                if company_update_fields:
                    await self.bitrix.call("crm.company.update", {
                        "id": company_id,
                        "fields": company_update_fields
                    })
                    logger.info(f"[Company {company_id}] Updated main card fields: {list(company_update_fields.keys())}")

                # 2. Бухгалтерия (Реквизиты)
                if needs_req_update:
                    if is_new:
                        PRESET_ID_IP = 5     # Твой ID шаблона ИП
                        PRESET_ID_LEGAL = 1  # Твой ID шаблона ООО
                        correct_preset_id = PRESET_ID_IP if is_ip else PRESET_ID_LEGAL

                        requisite_id = await self.bitrix.create_requisite(
                            entity_id=company_id,
                            preset_id=correct_preset_id,
                            unp=unp,
                            fields=fields_to_write,
                        )
                        logger.info(f"[Company {company_id}] Created new requisite ID={requisite_id} using preset {correct_preset_id}")
                    else:
                        requisite_id = int(requisite["ID"])
                        await self.bitrix.update_requisite(requisite_id, unp, fields_to_write)
                        logger.info(f"[Company {company_id}] Overwrote existing requisite ID={requisite_id}")
                        
            except BitrixAPIError as e:
                logger.error(f"[Company {company_id}] Error saving data: {e}")

            logger.info(f"[Company {company_id}] Processing completed successfully")

        except Exception as e:
            logger.error(f"[Company {company_id}] Critical error in process_company_update: {e}")