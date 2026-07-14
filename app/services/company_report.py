"""Excel dossier export for a single company."""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from typing import Any, Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.crud.company import CompanyCRUD
from app.database.models import CompanyEvent, GrpTaxpayerData, NalogDebtRecord
from app.services.company_relations import find_related_by_address, find_related_by_contact
from app.services.risk_scoring import compute_risk


EXCEL_CELL_LIMIT = 32_000
JSON_CHUNK_SIZE = 30_000
HEADER_FILL = PatternFill("solid", fgColor="1E3A5F")
HEADER_FONT = Font(color="FFFFFF", bold=True)


def _value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool, datetime)):
        text = value.isoformat() if isinstance(value, datetime) else value
    else:
        text = json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(text, str) and text.startswith(("=", "+", "-", "@")):
        text = "'" + text
    if isinstance(text, str) and len(text) > EXCEL_CELL_LIMIT:
        return text[: EXCEL_CELL_LIMIT - 16] + "… [сокращено]"
    return text


def _json_chunks(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return [text[index : index + JSON_CHUNK_SIZE] for index in range(0, len(text), JSON_CHUNK_SIZE)] or [""]


def _add_sheet(
    workbook: Workbook,
    title: str,
    columns: list[tuple[str, str]],
    rows: Iterable[dict[str, Any]],
) -> None:
    sheet = workbook.create_sheet(title=title[:31])
    sheet.append([label for _, label in columns])
    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    row_count = 0
    for row in rows:
        sheet.append([_value(row.get(key)) for key, _ in columns])
        row_count += 1

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{max(row_count + 1, 1)}"
    sheet.sheet_view.showGridLines = False
    for column_index, (_, label) in enumerate(columns, start=1):
        values = [str(label)]
        values.extend(str(sheet.cell(row=row_index, column=column_index).value or "") for row_index in range(2, min(row_count + 2, 102)))
        width = min(max(max(map(len, values)) + 2, 12), 60)
        sheet.column_dimensions[get_column_letter(column_index)].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)


def _event_rows(db: Session, company_id: Any) -> list[dict[str, Any]]:
    events = (
        db.query(CompanyEvent)
        .filter(CompanyEvent.company_id == company_id)
        .order_by(CompanyEvent.event_date.desc().nullslast(), CompanyEvent.created_at.desc())
        .all()
    )
    return [
        {
            "event_record_id": item.event_record_id,
            "event_type": item.event_type.name if item.event_type else None,
            "event_date": item.event_date,
            "cancel_date": item.cancel_date,
            "document_date": item.document_date,
            "deadline_date": item.deadline_date,
            "suspension_end_date": item.suspension_end_date,
            "document_number": item.document_number,
            "decision_authority": item.decision_authority.name if item.decision_authority else None,
            "document_authority": item.document_authority.name if item.document_authority else None,
            "foundation": item.foundation.name if item.foundation else None,
            "notes": item.notes,
        }
        for item in events
    ]


def _grp_rows(db: Session, unp: int) -> list[dict[str, Any]]:
    item = db.query(GrpTaxpayerData).filter(GrpTaxpayerData.unp == unp).first()
    if not item:
        return []
    return [
        {
            "full_name": item.full_name,
            "short_name": item.short_name,
            "registration_date": item.registration_date,
            "inspectorate_code": item.inspectorate_code,
            "inspectorate_name": item.inspectorate_name,
            "status_code": item.status_code,
            "status_date": item.status_date,
            "address": item.address,
            "fetched_at": item.fetched_at,
            "updated_at": item.updated_at,
        }
    ]


def _tax_debt_rows(db: Session, unp: int) -> list[dict[str, Any]]:
    items = (
        db.query(NalogDebtRecord)
        .filter(NalogDebtRecord.debtor_unp == unp)
        .order_by(NalogDebtRecord.slice_date.desc(), NalogDebtRecord.debt_date.desc().nullslast())
        .all()
    )
    return [
        {
            "imns_code": item.imns_code,
            "imns_name": item.imns_name,
            "debt_date": item.debt_date,
            "repayment_date": item.repayment_date,
            "slice_date": item.slice_date,
        }
        for item in items
    ]


def build_company_report(db: Session, unp: int) -> bytes | None:
    company_crud = CompanyCRUD(db)
    profile = company_crud.get_full_dossier(unp)
    company = company_crud.get_by_unp(unp)
    if not profile or not company:
        return None

    bankruptcy = company_crud.get_bankrot_dossier(unp)
    grp_rows = _grp_rows(db, unp)
    tax_rows = _tax_debt_rows(db, unp)
    risk = compute_risk(db, unp) or {}
    related_by_contact = find_related_by_contact(db, company.id, limit=200)
    related_by_address = find_related_by_address(db, company.id, limit=200)
    events = _event_rows(db, company.id)

    workbook = Workbook()
    workbook.remove(workbook.active)
    workbook.properties.title = f"Досье компании {unp}"
    workbook.properties.subject = "Агрегированные данные по компании"
    workbook.properties.creator = "Tendex EGR Aggregator"

    counts = {
        "names": len(profile.get("names") or []),
        "addresses": len(profile.get("addresses") or []),
        "ved": len(profile.get("ved") or []),
        "contacts": len(profile.get("contacts_aggregated") or profile.get("contacts") or []),
        "events": len(events),
        "tax_debt": len(tax_rows),
        "bankruptcy": len(bankruptcy.get("cases") or []),
        "trade": len(profile.get("trade_registry_records") or []),
        "licenses": len(profile.get("license_records") or []),
        "inspections": len(profile.get("inspection_plan_records") or []),
        "related": len(related_by_contact) + len(related_by_address),
    }
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "unp": unp,
        "name": profile.get("current_name_ru") or profile.get("current_short_name_ru"),
        "status": profile.get("current_status_name"),
        "registration_date": profile.get("registration_date"),
        "liquidation_date": profile.get("liquidation_date"),
        "address": profile.get("place_location_address"),
        "latitude": profile.get("latitude"),
        "longitude": profile.get("longitude"),
        "risk_score": risk.get("score"),
        "risk_level": risk.get("level"),
        **{f"count_{key}": value for key, value in counts.items()},
    }
    _add_sheet(
        workbook,
        "Сводка",
        [
            ("generated_at", "Сформировано UTC"), ("unp", "УНП"), ("name", "Наименование"),
            ("status", "Статус"), ("registration_date", "Дата регистрации"),
            ("liquidation_date", "Дата ликвидации"), ("address", "Адрес"),
            ("latitude", "Широта"), ("longitude", "Долгота"),
            ("risk_score", "Риск, баллы"), ("risk_level", "Уровень риска"),
            ("count_names", "Названия"), ("count_addresses", "Адреса"),
            ("count_ved", "ВЭД"), ("count_contacts", "Контакты"),
            ("count_events", "События ЕГР"), ("count_tax_debt", "Записи МНС"),
            ("count_bankruptcy", "Дела о банкротстве"), ("count_trade", "Объекты МАРТ"),
            ("count_licenses", "Лицензии"), ("count_inspections", "Проверки"),
            ("count_related", "Связанные компании"),
        ],
        [summary],
    )

    _add_sheet(workbook, "Названия ЕГР", [("full_name_ru", "Полное RU"), ("short_name_ru", "Краткое RU"), ("full_name_by", "Полное BY"), ("valid_from", "С"), ("valid_to", "По")], profile.get("names") or [])
    _add_sheet(workbook, "Адреса ЕГР", [("full_address", "Адрес"), ("postal_code", "Индекс"), ("region", "Область"), ("district", "Район"), ("valid_from", "С"), ("valid_to", "По")], profile.get("addresses") or [])
    _add_sheet(workbook, "ВЭД ЕГР", [("ved_code", "Код"), ("ved_name", "Наименование"), ("valid_from", "С"), ("valid_to", "По")], profile.get("ved") or [])
    _add_sheet(workbook, "Контакты", [("contact_type", "Тип"), ("value", "Значение"), ("full_name", "Контактное лицо"), ("position", "Должность"), ("sources", "Источники"), ("email", "Email"), ("phone", "Телефон"), ("website", "Сайт"), ("fax", "Факс")], profile.get("contacts_aggregated") or profile.get("contacts") or [])
    _add_sheet(workbook, "События ЕГР", [("event_record_id", "ID"), ("event_type", "Тип"), ("event_date", "Дата"), ("cancel_date", "Отмена"), ("document_date", "Документ"), ("deadline_date", "Срок"), ("suspension_end_date", "Окончание приостановления"), ("document_number", "Номер документа"), ("decision_authority", "Орган решения"), ("document_authority", "Орган документа"), ("foundation", "Основание"), ("notes", "Примечание")], events)
    _add_sheet(workbook, "ГРП МНС", [("full_name", "Полное название"), ("short_name", "Краткое название"), ("registration_date", "Регистрация"), ("inspectorate_code", "Код инспекции"), ("inspectorate_name", "Инспекция"), ("status_code", "Статус"), ("status_date", "Дата статуса"), ("address", "Адрес"), ("fetched_at", "Получено"), ("updated_at", "Обновлено")], grp_rows)
    _add_sheet(workbook, "Задолженность МНС", [("imns_code", "Код ИМНС"), ("imns_name", "ИМНС"), ("debt_date", "Дата долга"), ("repayment_date", "Погашение"), ("slice_date", "Дата среза")], tax_rows)

    risk_rows = [{"kind": "risk", **item} for item in risk.get("factors") or []] + [{"kind": "trust", **item} for item in risk.get("trust_signals") or []]
    _add_sheet(workbook, "Риск-профиль", [("kind", "Тип"), ("code", "Код"), ("title", "Фактор"), ("weight", "Вес"), ("detail", "Детали")], risk_rows)
    _add_sheet(workbook, "Связи по контактам", [("unp", "УНП"), ("name", "Наименование"), ("matched_type", "Тип"), ("matched_value", "Совпадение")], related_by_contact)
    _add_sheet(workbook, "Связи по адресу", [("unp", "УНП"), ("name", "Наименование"), ("address", "Адрес")], related_by_address)

    pvt = profile.get("pvt_resident")
    _add_sheet(workbook, "ПВТ", [("name", "Наименование"), ("city", "Город"), ("legal_address", "Адрес"), ("phone", "Телефон"), ("website", "Сайт"), ("activity_directions", "Направления"), ("description", "Описание"), ("profile_url", "Профиль"), ("last_seen_at", "Проверено")], [pvt] if pvt else [])
    _add_sheet(workbook, "Торговый реестр МАРТ", [("registration_number", "Номер"), ("legal_name", "Юр. название"), ("legal_address", "Юр. адрес"), ("object_type", "Тип объекта"), ("object_name", "Объект"), ("internet_shop_domain", "Интернет-магазин"), ("trade_network_name", "Сеть"), ("object_region", "Область"), ("object_locality", "Населённый пункт"), ("object_street", "Улица"), ("object_building", "Дом"), ("object_office", "Помещение"), ("object_contacts", "Контакты"), ("goods_groups", "Группы товаров"), ("inclusion_date", "Включено"), ("source_date", "Дата источника")], profile.get("trade_registry_records") or [])
    accreditation = profile.get("gias_accreditation")
    _add_sheet(workbook, "ГИАС аккредитация", [("state", "Статус"), ("summary", "Описание"), ("phone", "Телефон"), ("email", "Email"), ("web_site", "Сайт"), ("city_name", "Город"), ("placements_address", "Адрес"), ("dt_from", "С"), ("dt_to", "По"), ("dt_update", "Обновлено")], [accreditation] if accreditation else [])
    _add_sheet(workbook, "ГИАС поставщики", [("state", "Статус"), ("name", "Наименование"), ("location", "Место"), ("reg_number", "Номер"), ("add_date", "Включён"), ("del_date", "Исключён"), ("base_incl_text", "Основание включения"), ("base_excl_text", "Основание исключения"), ("author_initials", "Автор")], profile.get("gias_locked_suppliers") or [])
    _add_sheet(workbook, "ЕАЭС и СЭЗ", [("country", "Страна"), ("full_name", "Название"), ("legal_address", "Адрес"), ("registration_agency", "Орган регистрации"), ("sez_name", "СЭЗ"), ("project_name", "Проект"), ("registry_entry_date", "Дата включения"), ("certificate", "Свидетельство"), ("source_url", "Источник")], profile.get("eaeu_sez_resident_records") or [])
    _add_sheet(workbook, "Лицензии", [("generated_number", "Номер"), ("holder_name", "Владелец"), ("activity_type_name", "Вид деятельности"), ("activity_date_start", "С"), ("activity_date_end", "По"), ("activity_is_active", "Активна"), ("last_seen_at", "Проверено")], profile.get("license_records") or [])
    _add_sheet(workbook, "Планы проверок", [("plan_period", "Период"), ("source_region", "Регион"), ("plan_title", "План"), ("plan_item_no", "Пункт"), ("approving_authority", "Утвердивший орган"), ("controller_unp", "УНП контролёра"), ("controller_authority", "Контролирующий орган"), ("executor_phone", "Телефон"), ("start_month", "Месяц"), ("source_file", "Источник")], profile.get("inspection_plan_records") or [])

    certificates = profile.get("belltpp_own_certificates") or []
    _add_sheet(workbook, "Сертификаты БелТПП", [("holder_name", "Владелец"), ("cert_number", "Номер"), ("blank_number", "Бланк"), ("issue_date", "Выдан"), ("valid_until", "Действует до"), ("verify_url", "Проверка"), ("last_seen_at", "Проверено")], certificates)
    product_rows = []
    for certificate in certificates:
        for product in certificate.get("products") or []:
            product_rows.append({"cert_number": certificate.get("cert_number"), **product})
    _add_sheet(workbook, "Продукция БелТПП", [("cert_number", "Сертификат"), ("row_no", "Строка"), ("name", "Продукция"), ("code", "Код")], product_rows)

    bankrot_cases = bankruptcy.get("cases") or []
    _add_sheet(workbook, "Дела о банкротстве", [("case_id", "ID"), ("number", "Номер"), ("start_date", "Начало"), ("end_date", "Окончание"), ("status", "Статус"), ("procedure_type", "Процедура"), ("court", "Суд"), ("judge", "Судья"), ("manager_id", "ID управляющего"), ("manager_name", "Управляющий"), ("last_judgment_id", "Последнее решение"), ("fetch_error", "Ошибка"), ("updated_at", "Обновлено")], bankrot_cases)
    dataset_rows = []
    for case in bankrot_cases:
        for dataset in case.get("datasets") or []:
            chunks = _json_chunks(dataset.get("payload"))
            for chunk_number, payload_chunk in enumerate(chunks, start=1):
                dataset_rows.append(
                    {
                        "case_id": case.get("case_id"),
                        "case_number": case.get("number"),
                        "dataset_type": dataset.get("dataset_type"),
                        "endpoint": dataset.get("endpoint"),
                        "http_method": dataset.get("http_method"),
                        "chunk_number": chunk_number,
                        "chunks_total": len(chunks),
                        "payload": payload_chunk,
                        "fetch_error": dataset.get("fetch_error"),
                        "fetched_at": dataset.get("fetched_at"),
                    }
                )
    _add_sheet(workbook, "Bankrot данные", [("case_id", "ID дела"), ("case_number", "Номер дела"), ("dataset_type", "Раздел"), ("endpoint", "Endpoint"), ("http_method", "Метод"), ("chunk_number", "Часть"), ("chunks_total", "Всего частей"), ("payload", "JSON payload"), ("fetch_error", "Ошибка"), ("fetched_at", "Получено")], dataset_rows)

    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()
