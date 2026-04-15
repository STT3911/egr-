import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class RequisiteService:
    def __init__(self, bitrix_client, egr_client):
        self.bitrix = bitrix_client
        self.egr = egr_client

    async def process_company_update(self, company_id: int):
        """Main processing logic for OnCrmCompanyUpdate."""
        logger.info(f"[Company {company_id}] Starting processing")

        try:
            # Загружаем настройки из БД
            cfg = await self.bitrix._load_settings()
            
            # Если поле в админке еще не сохранено, используем дефолтное
            unp_field_code = cfg.unp_field_code if cfg and cfg.unp_field_code else "UF_CRM_1775144152"
            
            # Шаг 1-3: Получаем компанию и УНП
            company = await self.bitrix.call("crm.company.get", {"id": company_id})
            company_title = company.get("TITLE", "")

            # Читаем УНП
            unp_raw = company.get(unp_field_code)  
            
            if not unp_raw or str(unp_raw).strip() == "":
                logger.info(f"[Company {company_id}] No UNP provided in field {unp_field_code}, skipping")
                return
                
            unp = str(unp_raw).strip()

            # Шаг 4: Идем в ЕГР
            egr_info = await self.egr.get_company_info(unp)
            
            if egr_info.is_empty:
                logger.info(f"[Company {company_id}] No data from EGR to write")
                return

            # --- Шаг 5: УМНОЕ ОПРЕДЕЛЕНИЕ ИП И ФОРМИРОВАНИЕ ПОЛЕЙ ---
            name_upper = (egr_info.full_name or "").upper()
            
            is_ip = False
            if "ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ" in name_upper or "ИП " in name_upper:
                is_ip = True
            # Если в УНП есть буквы — это 100% физлицо/ИП (правило налоговой РБ)
            elif not unp.isdigit():
                is_ip = True
            # Подстраховка: если в названии нет маркеров юрлица
            elif not any(org_type in name_upper for org_type in ["ООО", "ЗАО", "ОАО", "ЧУП", "ОДО", "УП ", "РУП", "ТОВАРИЩЕСТВО"]):
                is_ip = True

            fields_to_write = {}
            
            if is_ip:
                base_name = egr_info.short_name or egr_info.full_name
                
                # Динамические маски для ИП из базы данных
                mask_full = cfg.ip_mask_full if cfg and cfg.ip_mask_full else "Индивидуальный предприниматель {company_name}"
                mask_short = cfg.ip_mask_short if cfg and cfg.ip_mask_short else "ИП {company_name}"
                mask_basis = cfg.ip_mask_basis if cfg and cfg.ip_mask_basis else "Свидетельство о регистрации № {company_unp}"
                
                full_name_masked = mask_full.replace("{company_name}", egr_info.full_name)
                short_name_masked = mask_short.replace("{company_name}", base_name)
                basis_masked = mask_basis.replace("{company_unp}", unp).replace("{company_name}", base_name)
                
                fields_to_write["NAME"] = short_name_masked
                fields_to_write["RQ_COMPANY_NAME"] = short_name_masked
                fields_to_write["RQ_COMPANY_FULL_NAME"] = full_name_masked
                fields_to_write["RQ_LEGAL_FORM"] = basis_masked
            else:
                name = egr_info.short_name or egr_info.full_name
                fields_to_write["NAME"] = name
                fields_to_write["RQ_COMPANY_NAME"] = egr_info.short_name
                fields_to_write["RQ_COMPANY_FULL_NAME"] = egr_info.full_name
                if egr_info.authority:
                    fields_to_write["RQ_LEGAL_FORM"] = egr_info.authority[:80]
                    
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

            # Добавляем адрес (Тип 6 - Юридический)
            if egr_info.full_address:
                address_fields = {"ADDRESS_1": egr_info.full_address}
                if egr_info.postal_code:
                    address_fields["ZIP_CODE"] = str(egr_info.postal_code)
                if egr_info.region:
                    address_fields["REGION"] = egr_info.region
                fields_to_write["RQ_ADDR"] = {"6": address_fields}

            # Шаг 6: Получаем старые реквизиты компании
            try:
                req_list = await self.bitrix.call("crm.requisite.list", {
                    "filter": {
                        "ENTITY_ID": company_id, 
                        "ENTITY_TYPE_ID": 4,  
                        "RQ_INN": unp  # Ищем именно реквизит с таким же УНП!
                    }
                })
                requisite = req_list[0] if req_list else None
            except Exception as e:
                logger.error(f"[Company {company_id}] Error finding requisite: {e}")
                return
                
            is_new = requisite is None
            new_title = fields_to_write.get("RQ_COMPANY_NAME") or fields_to_write.get("NAME")

            # --- Шаг 7: ИСПРАВЛЕННАЯ ЗАЩИТА ОТ ЦИКЛА ---
            needs_title_update = bool(new_title and company_title != new_title)
            
            needs_req_update = False
            if is_new:
                needs_req_update = True
            else:
                for key in ["NAME", "RQ_COMPANY_FULL_NAME", "RQ_OKVED", "RQ_LEGAL_FORM", "RQ_OGRNIP"]:
                    if key in fields_to_write:
                        # Приводим к строке, чтобы None не триггерил обновление при сравнении с ""
                        old_val = str(requisite.get(key) or "").strip()
                        new_val = str(fields_to_write[key] or "").strip()
                        
                        if old_val != new_val:
                            needs_req_update = True
                            logger.info(f"[Company {company_id}] Requisite changed on field '{key}': '{old_val}' -> '{new_val}'")
                            break

            needs_contact_update = False 

            try:
                if hasattr(egr_info, 'phone') and egr_info.phone and not company.get("PHONE"):
                    needs_contact_update = True
                if hasattr(egr_info, 'email') and egr_info.email and not company.get("EMAIL"):
                    needs_contact_update = True
                if hasattr(egr_info, 'website') and egr_info.website and not company.get("WEB"):
                    needs_contact_update = True
            except Exception as e:
                logger.error(f"[Company {company_id}] Error checking current fields: {e}")

            if not any([needs_title_update, needs_req_update, needs_contact_update]):
                logger.info(f"[Company {company_id}] Битрикс и ЕГР синхронизированы. Останавливаемся (защита от цикла).")
                return

            # Шаг 8: Обновляем Битрикс!
            try:
                # 1. Фасад карточки
                company_update_fields = {}
                if needs_title_update:
                    company_update_fields["TITLE"] = new_title
                    
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
                        PRESET_ID_LEGAL = cfg.requisite_preset_id if cfg and cfg.requisite_preset_id else 1
                        PRESET_ID_IP = 5 
                        
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
                        
            except Exception as e:
                logger.error(f"[Company {company_id}] Error saving data: {e}")

            logger.info(f"[Company {company_id}] Processing completed successfully")

        except Exception as e:
            logger.error(f"[Company {company_id}] Critical error in process_company_update: {e}")
