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


# Bitrix строго валидирует e-mail и отклоняет весь crm.company.update при кривом адресе,
# а в ЕГР email часто мусорный/множественный. Берём первый валидный (строго ASCII,
# как ожидает Bitrix). Точки-разделители: без ведущей/висячей/двойной точки
# (напр. «nikolay.piv.@gmail.com» — невалиден).
_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9_%+\-]+(?:\.[A-Za-z0-9_%+\-]+)*"   # локальная часть
    r"@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*"          # домен
    r"\.[A-Za-z]{2,}$"                                # TLD
)


def _first_valid_email(value: str | None) -> str | None:
    """Первый корректный e-mail из строки (ЕГР может отдать несколько через , ; пробел)."""
    if not value:
        return None
    for part in re.split(r"[,;\s]+", value.strip()):
        if part and _EMAIL_RE.match(part):
            return part
    return None


def _normalize_unp(value: object) -> str | None:
    """Привести УНП к 9 цифрам: убрать пробелы/дефисы/«.0», оставить только цифры.

    Менеджеры вводят УНП по-разному («291 439 639», «291-439-639», «...0» из Excel),
    а тонкий эндпоинт принимает строго ^\\d{9}$ — поэтому нормализуем заранее.
    """
    if value is None:
        return None
    s = str(value).strip()
    if s.endswith(".0"):
        s = s[:-2]
    digits = re.sub(r"\D", "", s)
    return digits if len(digits) == 9 else None


def _quotes_to_guillemets(value: str | None) -> str | None:
    """Прямые кавычки "..." → ёлочки «...» в наименовании компании.

    Дополнительно вставляем пробел перед «, если ЕГР склеил форму с названием
    («предприятие«Смайл»» → «предприятие «Смайл»»).
    """
    if not value:
        return value
    value = re.sub(r'"([^"]*)"', r'«\1»', value)
    value = re.sub(r'(?<=\S)«', ' «', value)
    return value


def _to_by_intl(phone: str) -> str:
    """Белорусский междугородний выход «80…» → «+375…».

    По правилу РБ номер вида 80<код><номер> (80152…, 8029…) — это +375<код><номер>.
    Международные (+…) и прочие (без ведущего 80) не трогаем.
    """
    if not phone or phone.startswith("+"):
        return phone
    if not re.sub(r"\D", "", phone).startswith("80"):
        return phone
    removed = 0
    out: list[str] = []
    for ch in phone:
        if removed < 2 and ch.isdigit():  # срезаем ведущие 8 и 0
            removed += 1
            continue
        out.append(ch)
    return "+375" + "".join(out).lstrip(" -")


_PHONE_MIN_DIGITS = 6   # короче — почти всегда мусор («54321»)
_PHONE_MAX_COUNT = 5    # не засоряем карточку десятком номеров


def _split_phones(raw: str | None) -> list[str]:
    """Разобрать «телефонную» строку ЕГР в список номеров.

    В ЕГР это свободный текст: несколько номеров через ,/;, иногда с именами
    («Иванов И.И. - 8029-...») и мусором. Срезаем подпись перед номером,
    оставляем только телефонные символы, отбрасываем слишком короткие, дедуп.
    """
    if not raw:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for part in re.split(r"[,;]", raw):
        part = part.strip()
        if not part:
            continue
        # «Имя Фамилия - 8029-123-45-67» → берём то, что после последнего « - ».
        if " - " in part:
            part = part.rsplit(" - ", 1)[-1]
        # Оставляем только телефонные символы.
        cleaned = re.sub(r"[^0-9+()\s\-]", "", part)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
        if len(re.sub(r"\D", "", cleaned)) < _PHONE_MIN_DIGITS:
            continue
        cleaned = _to_by_intl(cleaned)
        key = re.sub(r"\D", "", cleaned)
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
        if len(result) >= _PHONE_MAX_COUNT:
            break
    return result


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
            
            unp = _normalize_unp(unp_raw)
            if not unp:
                logger.info(
                    f"[Company {company_id}] No valid 9-digit UNP in field {unp_field_code} "
                    f"(raw={unp_raw!r}), skipping"
                )
                return

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

            # Кавычки в наименованиях компании → ёлочки («...»), по регламенту.
            for _name_key in ("NAME", "RQ_COMPANY_NAME", "RQ_COMPANY_FULL_NAME"):
                if fields_to_write.get(_name_key):
                    fields_to_write[_name_key] = _quotes_to_guillemets(fields_to_write[_name_key])

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
                
            # Правило лида: если реквизит по этому УНП уже существует — НИЧЕГО не трогаем
            # (ни реквизит, ни карточку), чтобы не перезатирать правки, внесённые вручную.
            if requisite is not None:
                logger.info(f"[Company {company_id}] Requisite for UNP {unp} already exists (ID={requisite.get('ID')}) — skip, ничего не меняем")
                return

            # Реквизита по УНП ещё нет → первичное заполнение карточки и реквизита.
            new_title = fields_to_write.get("RQ_COMPANY_NAME") or fields_to_write.get("NAME")
            needs_title_update = bool(new_title and company_title != new_title)

            contact_email = _first_valid_email(getattr(egr_info, "email", None))
            contact_phones = _split_phones(getattr(egr_info, "phone", None))
            needs_contact_update = False
            try:
                if contact_phones and not company.get("PHONE"):
                    needs_contact_update = True
                if contact_email and not company.get("EMAIL"):
                    needs_contact_update = True
                if getattr(egr_info, "website", "") and not company.get("WEB"):
                    needs_contact_update = True
            except Exception as e:
                logger.error(f"[Company {company_id}] Error checking current fields: {e}")

            # Шаг 8: Обновляем Битрикс!
            # Сначала создаём реквизит и адрес, потом карточку — иначе обновление карточки
            # повторно дёрнет webhook раньше создания реквизита и появится дубль.
            requisite_id = None
            try:
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

                # Юридический адрес — отдельным вызовом через crm.address.*
                if address_fields and requisite_id:
                    address_type_id = await self.bitrix.get_address_type_id()
                    if await self.bitrix.upsert_requisite_address(requisite_id, address_type_id, address_fields):
                        logger.info(f"[Company {company_id}] Legal address written to requisite ID={requisite_id}")
                    else:
                        logger.warning(f"[Company {company_id}] Failed to write legal address to requisite ID={requisite_id}")
            except Exception as e:
                logger.error(f"[Company {company_id}] Error saving requisite: {e}")

            # Карточка (заголовок + контакты) — после реквизита. Отдельный try, чтобы
            # кривой контакт (Битрикс отклоняет весь апдейт) не ронял остальное.
            company_update_fields = {}
            if needs_title_update:
                company_update_fields["TITLE"] = new_title
            if needs_contact_update:
                if contact_phones:
                    company_update_fields["PHONE"] = [{"VALUE": p, "VALUE_TYPE": "WORK"} for p in contact_phones]
                if contact_email:
                    company_update_fields["EMAIL"] = [{"VALUE": contact_email, "VALUE_TYPE": "WORK"}]
                if getattr(egr_info, "website", ""):
                    company_update_fields["WEB"] = [{"VALUE": egr_info.website, "VALUE_TYPE": "WORK"}]

            if company_update_fields:
                try:
                    await self.bitrix.call("crm.company.update", {
                        "id": company_id,
                        "fields": company_update_fields,
                    })
                    logger.info(f"[Company {company_id}] Updated main card fields: {list(company_update_fields.keys())}")
                except Exception as e:
                    logger.error(f"[Company {company_id}] Card update failed: {e}")
                    # Повтор без EMAIL (частый виновник — кривой адрес из ЕГР).
                    retry_fields = {k: v for k, v in company_update_fields.items() if k != "EMAIL"}
                    if retry_fields:
                        try:
                            await self.bitrix.call("crm.company.update", {
                                "id": company_id,
                                "fields": retry_fields,
                            })
                            logger.info(f"[Company {company_id}] Card updated without EMAIL: {list(retry_fields.keys())}")
                        except Exception as e2:
                            logger.error(f"[Company {company_id}] Card retry failed: {e2}")

            logger.info(f"[Company {company_id}] Processing completed successfully")

        except Exception as e:
            logger.error(f"[Company {company_id}] Critical error in process_company_update: {e}")
