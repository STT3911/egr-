import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

# Префикс страны в начале адреса ЕГР — в реквизит Битрикса не пишем (по требованию).
_COUNTRY_PREFIX_RE = re.compile(r"^\s*(республика\s+)?беларусь\s*,?\s*", re.IGNORECASE)


def _strip_country_prefix(address: str | None) -> str:
    """Убрать ведущее «Республика Беларусь,» из строки адреса."""
    if not address:
        return ""
    return _COUNTRY_PREFIX_RE.sub("", address).strip()


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

            # --- Шаг 5: ОПРЕДЕЛЕНИЕ ИП И ФОРМИРОВАНИЕ ПОЛЕЙ ---
            # Тип плательщика отдаёт тонкий эндпоинт сервиса; локальная эвристика — фолбэк.
            if egr_info.is_ip is not None:
                is_ip = egr_info.is_ip
            else:
                # Фолбэк, если сервис не вернул тип: учитываем оба наименования,
                # а при неопределённости считаем ОРГАНИЗАЦИЕЙ (не лепим «ИП» на юрлицо).
                text = f"{egr_info.full_name or ''} {egr_info.short_name or ''}".upper().strip()
                org_markers = (
                    "ООО", "ЗАО", "ОАО", "ПАО", "ЧУП", "ОДО", "УП ", "РУП", "КУП", "ТУП",
                    "ОБЩЕСТВО", "АКЦИОНЕРНОЕ", "УНИТАРНОЕ", "ПРЕДПРИЯТИЕ", "УЧРЕЖДЕНИЕ",
                    "КООПЕРАТИВ", "ТОВАРИЩЕСТВО", "КОНЦЕРН", "ХОЛДИНГ", "ОРГАНИЗАЦИЯ",
                )
                if "ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ" in text or text.startswith("ИП "):
                    is_ip = True
                elif not unp.isdigit():
                    is_ip = True
                elif any(marker in text for marker in org_markers):
                    is_ip = False
                else:
                    is_ip = False

            fields_to_write = {}
            
            if is_ip:
                base_name = egr_info.short_name or egr_info.full_name
                # ФИО без префикса «ИП»/«Индивидуальный предприниматель» — иначе маска
                # задвоит его («Индивидуальный предприниматель ИП Иванов…»).
                clean_name = egr_info.director or base_name

                # Динамические маски для ИП из базы данных
                mask_full = cfg.ip_mask_full if cfg and cfg.ip_mask_full else "Индивидуальный предприниматель {company_name}"
                mask_short = cfg.ip_mask_short if cfg and cfg.ip_mask_short else "ИП {company_name}"
                mask_basis = cfg.ip_mask_basis if cfg and cfg.ip_mask_basis else "Свидетельство о регистрации № {company_unp}"

                def _apply_mask(mask: str) -> str:
                    # Обе переменные доступны в любой маске.
                    return (
                        (mask or "")
                        .replace("{company_name}", clean_name or "")
                        .replace("{company_unp}", unp)
                    )

                short_name_masked = _apply_mask(mask_short)
                fields_to_write["NAME"] = short_name_masked
                fields_to_write["RQ_COMPANY_NAME"] = short_name_masked
                fields_to_write["RQ_COMPANY_FULL_NAME"] = _apply_mask(mask_full)
                # «Основание действия» в BY-схеме — поле RQ_BASE_DOC (RQ_LEGAL_FORM на форму не выводится).
                fields_to_write["RQ_BASE_DOC"] = _apply_mask(mask_basis)
                # Для ИП директора тоже заполняем — это ФИО самого предпринимателя.
                if egr_info.director:
                    fields_to_write["RQ_DIRECTOR"] = egr_info.director
            else:
                name = egr_info.short_name or egr_info.full_name
                fields_to_write["NAME"] = name
                fields_to_write["RQ_COMPANY_NAME"] = egr_info.short_name or egr_info.full_name
                fields_to_write["RQ_COMPANY_FULL_NAME"] = egr_info.full_name
                # Для юрлица «Основание действия» не заполняем — основание неизвестно
                # (заполняется только у ИП: «Свидетельство о регистрации № {УНП}»).
                if egr_info.authority:
                    fields_to_write["RQ_LEGAL_FORM"] = egr_info.authority[:80]
                if egr_info.director:
                    fields_to_write["RQ_DIRECTOR"] = egr_info.director
                    
            # Добавляем ОКЭД
            if egr_info.ved_code:
                fields_to_write["RQ_OKVED"] = egr_info.ved_code

            # Дата гос. регистрации. В белорусской схеме реквизитов поле называется
            # RQ_COMPANY_REG_DATE (тип string), а не RQ_STATE_REG_DATE (его в BY-схеме нет).
            if egr_info.registration_date:
                try:
                    dt = datetime.strptime(egr_info.registration_date, "%Y-%m-%d")
                    fields_to_write["RQ_COMPANY_REG_DATE"] = dt.strftime("%d.%m.%Y")
                except ValueError:
                    pass

            # Юридический адрес из БД. Пишем его отдельным вызовом crm.address.*
            # после создания/обновления реквизита (надёжнее поля RQ_ADDR).
            # Имена полей — штатные для адресов Битрикса (POSTAL_CODE, PROVINCE).
            address_fields: dict | None = None
            if egr_info.full_address:
                address_fields = {"ADDRESS_1": _strip_country_prefix(egr_info.full_address)}
                if egr_info.postal_code:
                    address_fields["POSTAL_CODE"] = str(egr_info.postal_code)
                if egr_info.region:
                    address_fields["PROVINCE"] = egr_info.region

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
            elif address_fields:
                # Адрес пишется отдельным вызовом и надёжно не сравнивается со старым
                # значением. Если адрес у нас есть — заходим в ветку обновления.
                needs_req_update = True
            else:
                for key in [
                    "NAME", "RQ_COMPANY_NAME", "RQ_COMPANY_FULL_NAME", "RQ_OKVED",
                    "RQ_LEGAL_FORM", "RQ_BASE_DOC", "RQ_OGRNIP", "RQ_DIRECTOR", "RQ_COMPANY_REG_DATE",
                ]:
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
                        # Единый Preset для ИП и организаций — для ИП отличаются только
                        # значения полей (по маскам), а не шаблон реквизита.
                        preset_id = cfg.requisite_preset_id if cfg and cfg.requisite_preset_id else 1

                        requisite_id = await self.bitrix.create_requisite(
                            entity_id=company_id,
                            preset_id=preset_id,
                            unp=unp,
                            fields=fields_to_write,
                        )

                        logger.info(f"[Company {company_id}] Created new requisite ID={requisite_id} using preset {preset_id}")
                    else:
                        requisite_id = int(requisite["ID"])
                        await self.bitrix.update_requisite(requisite_id, unp, fields_to_write)
                        logger.info(f"[Company {company_id}] Overwrote existing requisite ID={requisite_id}")

                    # Юридический адрес — отдельным вызовом через crm.address.*
                    if address_fields and requisite_id:
                        address_type_id = await self.bitrix.get_address_type_id()
                        if await self.bitrix.upsert_requisite_address(requisite_id, address_type_id, address_fields):
                            logger.info(f"[Company {company_id}] Legal address written to requisite ID={requisite_id}")
                        else:
                            logger.warning(f"[Company {company_id}] Failed to write legal address to requisite ID={requisite_id}")


            except Exception as e:
                logger.error(f"[Company {company_id}] Error saving data: {e}")

            logger.info(f"[Company {company_id}] Processing completed successfully")

        except Exception as e:
            logger.error(f"[Company {company_id}] Critical error in process_company_update: {e}")
