"""Message formatting helpers for the Telegram bot."""
from __future__ import annotations

from html import escape
from typing import Any

TELEGRAM_MESSAGE_LIMIT = 3900


HELP_TEXT = (
    "Напишите УНП или часть названия компании.\n\n"
    "<b>Поиск:</b>\n"
    "500000306\n"
    "минский автомобильный\n\n"
    "<b>Подписки на изменения ЕГР:</b>\n"
    "/subscribe 193712492 — подписаться на компанию\n"
    "/unsubscribe 193712492 — отменить подписку\n"
    "/mysubs — мои подписки\n\n"
    "Веб-аккаунт подключается одноразовой ссылкой из центра событий.\n\n"
    "<b>Подробный отчёт по всем источникам:</b>\n"
    "/more 193712492 — собрать полное досье\n"
    "Также можно ответить командой /more на сообщение с УНП."
)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"


def _format_period(item: dict[str, Any]) -> str | None:
    valid_from = _clean(item.get("valid_from"))
    valid_to = _clean(item.get("valid_to"))
    if valid_from and valid_to:
        return f"{valid_from} - {valid_to}"
    if valid_from:
        return f"с {valid_from}"
    if valid_to:
        return f"до {valid_to}"
    return None


def _format_trade_address(item: dict[str, Any]) -> str | None:
    parts = [
        _clean(item.get("object_region")),
        _clean(item.get("object_district")),
        _clean(item.get("object_locality")),
        _clean(item.get("object_street")),
        _clean(item.get("object_building")),
        _clean(item.get("object_office")),
    ]
    value = ", ".join(part for part in parts if part)
    return value or None


def _append_limited(lines: list[str], line: str, *, limit: int = TELEGRAM_MESSAGE_LIMIT) -> bool:
    candidate = "\n".join([*lines, line])
    if len(candidate) <= limit:
        lines.append(line)
        return True
    if lines and lines[-1] != "…":
        lines.append("…")
    return False


def _append_section(lines: list[str], title: str, section_lines: list[str]) -> None:
    if not section_lines:
        return
    _append_limited(lines, "")
    if not _append_limited(lines, f"<b>{escape(title)}</b>"):
        return
    for line in section_lines:
        if not _append_limited(lines, line):
            return


def company_display_name(company: dict[str, Any]) -> str:
    return (
        _clean(company.get("current_name_ru"))
        or _clean(company.get("current_short_name_ru"))
        or _clean(company.get("current_name_by"))
        or _clean(company.get("name"))
        or "Без названия"
    )


def lookup_display_name(item: dict[str, Any]) -> str:
    return (
        _clean(item.get("full_name_ru"))
        or _clean(item.get("short_name_ru"))
        or _clean(item.get("full_name_by"))
        or _clean(item.get("name"))
        or "Без названия"
    )


def lookup_button_text(item: dict[str, Any]) -> str:
    unp = _clean(item.get("unp")) or ""
    name = lookup_display_name(item)
    return _truncate(f"{unp} · {name}", 64)


def format_lookup_message(query: str, results: list[dict[str, Any]]) -> str:
    if not results:
        return f"По запросу «{escape(query)}» ничего не найдено."

    lines = [f"Нашёл {len(results)} вариантов по запросу «{escape(query)}»:"]
    for index, item in enumerate(results, start=1):
        unp = escape(_clean(item.get("unp")) or "")
        name = escape(lookup_display_name(item))
        lines.append(f"{index}. <b>{name}</b>\nУНП: <code>{unp}</code>")

        matched_name = _clean(item.get("matched_name"))
        if item.get("matched_historical_name") and matched_name:
            lines.append(
                "Найдено по прежнему названию: "
                f"{escape(_truncate(matched_name, 160))}"
            )

    lines.append("\nВыберите компанию кнопкой ниже.")
    return "\n".join(lines)


def format_company_card(company: dict[str, Any]) -> str:
    name = company_display_name(company)
    lines = [f"<b>{escape(name)}</b>"]

    unp = _clean(company.get("unp"))
    if unp:
        lines.append(f"УНП: <code>{escape(unp)}</code>")

    status = _clean(company.get("current_status_name"))
    status_code = _clean(company.get("current_status_code"))
    if status:
        lines.append(f"Статус: {escape(status)}")
    elif status_code:
        lines.append(f"Статус: код {escape(status_code)}")

    registration_date = _clean(company.get("registration_date"))
    if registration_date:
        lines.append(f"Дата регистрации: {escape(registration_date)}")

    liquidation_date = _clean(company.get("liquidation_date"))
    if liquidation_date:
        lines.append(f"Дата ликвидации: {escape(liquidation_date)}")

    short_name = _clean(company.get("current_short_name_ru"))
    if short_name and short_name != name:
        lines.append(f"Краткое название: {escape(short_name)}")

    name_by = _clean(company.get("current_name_by"))
    if name_by:
        lines.append(f"Название BY: {escape(name_by)}")

    address = _clean(company.get("place_location_address"))
    if address:
        lines.append(f"Адрес местонахождения: {escape(address)}")

    name_lines = []
    for index, item in enumerate(company.get("names") or [], start=1):
        values = []
        full_name = _clean(item.get("full_name_ru"))
        short = _clean(item.get("short_name_ru"))
        by = _clean(item.get("full_name_by"))
        period = _format_period(item)
        if full_name:
            values.append(escape(full_name))
        if short and short != full_name:
            values.append(f"кратко: {escape(short)}")
        if by:
            values.append(f"BY: {escape(by)}")
        if period:
            values.append(escape(period))
        if values:
            name_lines.append(f"{index}. " + "; ".join(values))
    _append_section(lines, "Названия", name_lines)

    address_lines = []
    for index, item in enumerate(company.get("addresses") or [], start=1):
        parts = []
        postal_code = _clean(item.get("postal_code"))
        region = _clean(item.get("region"))
        district = _clean(item.get("district"))
        full_address = _clean(item.get("full_address"))
        period = _format_period(item)
        if postal_code:
            parts.append(escape(postal_code))
        if region:
            parts.append(escape(region))
        if district:
            parts.append(escape(district))
        if full_address:
            parts.append(escape(full_address))
        if period:
            parts.append(escape(period))
        if parts:
            address_lines.append(f"{index}. " + "; ".join(parts))
    _append_section(lines, "Адреса", address_lines)

    ved_lines = []
    for index, item in enumerate(company.get("ved") or [], start=1):
        ved_code = _clean(item.get("ved_code"))
        ved_name = _clean(item.get("ved_name"))
        period = _format_period(item)
        if ved_code or ved_name:
            value = " ".join(part for part in [ved_code, ved_name] if part)
            if period:
                value = f"{value}; {period}"
            ved_lines.append(f"{index}. {escape(value)}")
    _append_section(lines, "ВЭД", ved_lines)

    contact_lines = []
    for index, item in enumerate(company.get("contacts") or [], start=1):
        parts = []
        email = _clean(item.get("email"))
        website = _clean(item.get("website"))
        phone = _clean(item.get("phone"))
        fax = _clean(item.get("fax"))
        if email:
            parts.append(f"Email: {escape(email)}")
        if website:
            parts.append(f"сайт: {escape(website)}")
        if phone:
            parts.append(f"телефон: {escape(phone)}")
        if fax:
            parts.append(f"факс: {escape(fax)}")
        if parts:
            contact_lines.append(f"{index}. " + "; ".join(parts))
    _append_section(lines, "Контакты", contact_lines)

    pvt = company.get("pvt_resident") or {}
    pvt_lines = []
    pvt_name = _clean(pvt.get("name"))
    pvt_description = _clean(pvt.get("description"))
    pvt_profile_url = _clean(pvt.get("profile_url"))
    if pvt_name:
        pvt_lines.append(f"Наименование: {escape(pvt_name)}")
    if pvt_description:
        pvt_lines.append(f"Описание: {escape(_truncate(pvt_description, 500))}")
    if pvt_profile_url:
        pvt_lines.append(f'<a href="{escape(pvt_profile_url)}">Профиль на park.by</a>')
    _append_section(lines, "Резидент ПВТ", pvt_lines)

    trade_records = company.get("trade_registry_records") or []
    trade_lines = []
    if trade_records:
        trade_lines.append(f"Записей: {len(trade_records)}")
    for index, item in enumerate(trade_records[:5], start=1):
        parts = []
        title = (
            _clean(item.get("object_name"))
            or _clean(item.get("internet_shop_domain"))
            or _clean(item.get("trade_network_name"))
            or _clean(item.get("object_type"))
            or f"Запись {index}"
        )
        parts.append(escape(_truncate(title, 180)))
        registration_number = _clean(item.get("registration_number"))
        if registration_number:
            parts.append(f"№ {escape(registration_number)}")
        object_type = _clean(item.get("object_type"))
        if object_type and object_type != title:
            parts.append(f"тип: {escape(_truncate(object_type, 120))}")
        address = _format_trade_address(item)
        if address:
            parts.append(f"адрес: {escape(_truncate(address, 180))}")
        inclusion_date = _clean(item.get("inclusion_date"))
        if inclusion_date:
            parts.append(f"включено: {escape(inclusion_date)}")
        trade_lines.append(f"{index}. " + "; ".join(parts))
    if len(trade_records) > 5:
        trade_lines.append(f"Показаны первые 5 из {len(trade_records)}")
    _append_section(lines, "Торговый реестр МАРТ", trade_lines)

    accreditation = company.get("gias_accreditation") or {}
    accreditation_lines = []
    for label, key in [
        ("Статус", "state"),
        ("Наименование", "summary"),
        ("Телефон", "phone"),
        ("Email", "email"),
        ("Сайт", "web_site"),
        ("Город", "city_name"),
        ("Адрес", "placements_address"),
        ("Обновлено", "dt_update"),
        ("Действует с", "dt_from"),
        ("Действует до", "dt_to"),
    ]:
        value = _clean(accreditation.get(key))
        if value:
            accreditation_lines.append(f"{label}: {escape(value)}")
    _append_section(lines, "ГИАС аккредитация", accreditation_lines)

    locked_supplier_lines = []
    for index, item in enumerate(company.get("gias_locked_suppliers") or [], start=1):
        parts = []
        for label, key in [
            ("Статус", "state"),
            ("Наименование", "name"),
            ("Место", "location"),
            ("Реестр", "reg_number"),
            ("Включен", "add_date"),
            ("Исключен", "del_date"),
            ("Основание включения", "base_incl_text"),
            ("Основание исключения", "base_excl_text"),
            ("Автор", "author_initials"),
        ]:
            value = _clean(item.get(key))
            if value:
                parts.append(f"{label}: {escape(_truncate(value, 220))}")
        if parts:
            locked_supplier_lines.append(f"{index}. " + "; ".join(parts))
    _append_section(lines, "ГИАС недобросовестные поставщики", locked_supplier_lines)

    return "\n".join(lines)


def _detail_fields(
    data: dict[str, Any],
    fields: list[tuple[str, str]],
    *,
    max_length: int = 500,
) -> list[str]:
    lines = []
    for label, key in fields:
        value = _clean(data.get(key))
        if value:
            lines.append(f"{escape(label)}: {escape(_truncate(value, max_length))}")
    return lines


def _detail_records(
    records: list[dict[str, Any]],
    fields: list[tuple[str, str]],
    *,
    limit: int = 20,
) -> list[str]:
    lines = []
    for index, record in enumerate(records[:limit], start=1):
        parts = []
        for label, key in fields:
            value = _clean(record.get(key))
            if value:
                parts.append(f"{escape(label)}: {escape(_truncate(value, 350))}")
        if parts:
            lines.append(f"{index}. " + "; ".join(parts))
    if len(records) > limit:
        lines.append(f"Показаны первые {limit} из {len(records)} записей.")
    return lines


def _detail_messages(title: str, lines: list[str]) -> list[str]:
    if not lines:
        return []
    header = f"<b>{escape(title)}</b>"
    messages = []
    current = [header]
    for line in lines:
        candidate = "\n".join([*current, line])
        if len(candidate) <= TELEGRAM_MESSAGE_LIMIT:
            current.append(line)
            continue
        messages.append("\n".join(current))
        current = [header, line]
    if len(current) > 1:
        messages.append("\n".join(current))
    return messages


def _dataset_size(payload: Any) -> str | None:
    if isinstance(payload, list):
        return f"{len(payload)} записей"
    if isinstance(payload, dict):
        for key in ("items", "content", "data", "results", "messages"):
            value = payload.get(key)
            if isinstance(value, list):
                return f"{len(value)} записей"
        return f"{len(payload)} полей"
    return None


def format_detailed_company_report(report: dict[str, Any]) -> list[str]:
    profile = report.get("profile") or {}
    errors = report.get("errors") or {}
    unp = _clean(profile.get("unp")) or "—"
    name = company_display_name(profile)
    bankruptcy = report.get("bankruptcy") or {}
    tax_debt = report.get("tax_debt") or {}
    related = report.get("related") or {}
    risk = report.get("risk") or {}
    grp = report.get("grp") or {}

    def source_state(source: str, has_data: bool, count: int | None = None) -> str:
        if source in errors:
            return f"⚠️ ошибка ({escape(str(errors[source]))})"
        if has_data:
            return f"✅ {count}" if count is not None else "✅ данные найдены"
        return "▫️ данных нет"

    trade_records = profile.get("trade_registry_records") or []
    locked_suppliers = profile.get("gias_locked_suppliers") or []
    eaeu_records = profile.get("eaeu_sez_resident_records") or []
    licenses = profile.get("license_records") or []
    inspections = profile.get("inspection_plan_records") or []
    certificates = profile.get("belltpp_own_certificates") or []
    bankrot_cases = bankruptcy.get("cases") or []
    tax_items = tax_debt.get("items") or []
    related_count = len(related.get("by_contact") or []) + len(related.get("by_address") or [])

    summary_lines = [
        f"<b>{escape(name)}</b>",
        f"УНП: <code>{escape(unp)}</code>",
        "",
        "<b>Проверенные источники</b>",
        "✅ ЕГР — основная карточка и история",
        f"{source_state('grp', bool(grp))} — ГРП МНС",
        f"{source_state('tax_debt', bool(tax_items), len(tax_items))} — задолженность МНС",
        f"{source_state('bankruptcy', bool(bankrot_cases), len(bankrot_cases))} — bankrot.gov.by",
        f"{source_state('risk', bool(risk))} — риск-профиль",
        f"{source_state('related', related_count > 0, related_count)} — связанные компании",
        f"{source_state('trade', bool(trade_records), len(trade_records))} — торговый реестр МАРТ",
        f"{source_state('gias', bool(profile.get('gias_accreditation')) or bool(locked_suppliers), len(locked_suppliers))} — ГИАС",
        f"{source_state('pvt', bool(profile.get('pvt_resident')))} — ПВТ",
        f"{source_state('eaeu', bool(eaeu_records), len(eaeu_records))} — реестры ЕАЭС/СЭЗ",
        f"{source_state('licenses', bool(licenses), len(licenses))} — лицензии",
        f"{source_state('inspections', bool(inspections), len(inspections))} — планы проверок",
        f"{source_state('certificates', bool(certificates), len(certificates))} — БелТПП",
    ]
    messages = ["\n".join(summary_lines)]

    egr_lines = _detail_fields(
        profile,
        [
            ("Статус", "current_status_name"),
            ("Код статуса", "current_status_code"),
            ("Дата регистрации", "registration_date"),
            ("Дата ликвидации", "liquidation_date"),
            ("Текущее название", "current_name_ru"),
            ("Краткое название", "current_short_name_ru"),
            ("Название BY", "current_name_by"),
            ("Адрес", "place_location_address"),
        ],
    )
    names = profile.get("names") or []
    if names:
        egr_lines.append(f"\n<b>История названий ({len(names)})</b>")
        egr_lines.extend(
            _detail_records(
                names,
                [
                    ("название", "full_name_ru"),
                    ("кратко", "short_name_ru"),
                    ("с", "valid_from"),
                    ("по", "valid_to"),
                ],
            )
        )
    addresses = profile.get("addresses") or []
    if addresses:
        egr_lines.append(f"\n<b>История адресов ({len(addresses)})</b>")
        egr_lines.extend(
            _detail_records(
                addresses,
                [("адрес", "full_address"), ("с", "valid_from"), ("по", "valid_to")],
            )
        )
    ved = profile.get("ved") or []
    if ved:
        egr_lines.append(f"\n<b>Виды деятельности ({len(ved)})</b>")
        egr_lines.extend(
            _detail_records(
                ved,
                [("код", "ved_code"), ("вид", "ved_name"), ("с", "valid_from"), ("по", "valid_to")],
            )
        )
    contacts = profile.get("contacts_aggregated") or profile.get("contacts") or []
    if contacts:
        egr_lines.append(f"\n<b>Контакты ({len(contacts)})</b>")
        egr_lines.extend(
            _detail_records(
                contacts,
                [
                    ("тип", "contact_type"),
                    ("значение", "value"),
                    ("телефон", "phone"),
                    ("email", "email"),
                    ("сайт", "website"),
                    ("источники", "sources"),
                ],
            )
        )
    messages.extend(_detail_messages("🏢 ЕГР — полная карточка", egr_lines))

    if grp:
        messages.extend(
            _detail_messages(
                "🏛 ГРП МНС",
                _detail_fields(
                    grp,
                    [
                        ("Полное название", "full_name"),
                        ("Краткое название", "short_name"),
                        ("Дата регистрации", "registration_date"),
                        ("Инспекция", "inspectorate_name"),
                        ("Код инспекции", "inspectorate_code"),
                        ("Статус", "status_code"),
                        ("Дата статуса", "status_date"),
                        ("Адрес", "address"),
                        ("Получено", "fetched_at"),
                        ("Обновлено", "updated_at"),
                        ("Последняя ошибка", "last_error"),
                    ],
                ),
            )
        )

    if risk:
        level_labels = {"high": "высокий", "medium": "средний", "low": "низкий"}
        risk_lines = [
            f"Оценка: <b>{escape(_clean(risk.get('score')) or '0')}/100</b>",
            f"Уровень: {escape(level_labels.get(risk.get('level'), _clean(risk.get('level')) or '—'))}",
        ]
        factors = risk.get("factors") or []
        if factors:
            risk_lines.append("\n<b>Факторы риска</b>")
            risk_lines.extend(
                _detail_records(factors, [("фактор", "title"), ("вес", "weight"), ("детали", "detail")])
            )
        trust = risk.get("trust_signals") or []
        if trust:
            risk_lines.append("\n<b>Сигналы доверия</b>")
            risk_lines.extend(
                _detail_records(trust, [("сигнал", "title"), ("вес", "weight"), ("детали", "detail")])
            )
        messages.extend(_detail_messages("📊 Риск-профиль", risk_lines))

    if bankrot_cases:
        bankrot_lines = []
        for index, case in enumerate(bankrot_cases, start=1):
            datasets = case.get("datasets") or []
            successful = sum(1 for item in datasets if not item.get("fetch_error"))
            bankrot_lines.append(f"\n<b>Дело {index}: {escape(_clean(case.get('number')) or str(case.get('case_id') or '—'))}</b>")
            bankrot_lines.extend(
                _detail_fields(
                    case,
                    [
                        ("Начало", "start_date"),
                        ("Окончание", "end_date"),
                        ("Статус", "status"),
                        ("Процедура", "procedure_type"),
                        ("Суд", "court"),
                        ("Судья", "judge"),
                        ("Управляющий", "manager_name"),
                        ("Ошибка карточки", "fetch_error"),
                    ],
                )
            )
            bankrot_lines.append(f"Наборы данных: {successful}/{len(datasets)} успешно")
            for dataset in datasets:
                dataset_type = escape(_clean(dataset.get("dataset_type")) or "unknown")
                if dataset.get("fetch_error"):
                    bankrot_lines.append(f"⚠️ {dataset_type}: {escape(_truncate(str(dataset['fetch_error']), 250))}")
                else:
                    size = _dataset_size(dataset.get("payload"))
                    suffix = f" — {escape(size)}" if size else ""
                    bankrot_lines.append(f"✅ {dataset_type}{suffix}")
        messages.extend(_detail_messages("⚖️ Банкротство — полное досье", bankrot_lines))

    if tax_items:
        tax_lines = [
            f"Записей: {len(tax_items)}",
            f"Последний срез: {escape(_clean(tax_debt.get('latest_slice_date')) or '—')}",
        ]
        tax_lines.extend(
            _detail_records(
                tax_items,
                [
                    ("ИМНС", "imns_name"),
                    ("код", "imns_code"),
                    ("дата долга", "debt_date"),
                    ("погашение", "repayment_date"),
                    ("срез", "slice_date"),
                ],
                limit=30,
            )
        )
        messages.extend(_detail_messages("💰 Задолженность МНС", tax_lines))

    if related_count:
        related_lines = []
        by_address = related.get("by_address") or []
        if by_address:
            related_lines.append(f"<b>По адресу ({len(by_address)})</b>")
            related_lines.extend(_detail_records(by_address, [("УНП", "unp"), ("название", "name"), ("адрес", "address")]))
        by_contact = related.get("by_contact") or []
        if by_contact:
            related_lines.append(f"\n<b>По контактам ({len(by_contact)})</b>")
            related_lines.extend(
                _detail_records(
                    by_contact,
                    [("УНП", "unp"), ("название", "name"), ("тип", "matched_type"), ("совпадение", "matched_value")],
                )
            )
        messages.extend(_detail_messages("🔗 Связанные компании", related_lines))

    pvt = profile.get("pvt_resident") or {}
    if pvt:
        pvt_lines = _detail_fields(
            pvt,
            [
                ("Название", "name"),
                ("Город", "city"),
                ("Адрес", "legal_address"),
                ("Телефон", "phone"),
                ("Сайт", "website"),
                ("Описание", "description"),
                ("Профиль", "profile_url"),
                ("Обновлено", "last_seen_at"),
            ],
        )
        directions = pvt.get("activity_directions") or []
        if directions:
            pvt_lines.append("Направления: " + escape(", ".join(map(str, directions))))
        messages.extend(_detail_messages("💻 Парк высоких технологий", pvt_lines))

    if trade_records:
        messages.extend(
            _detail_messages(
                "🏪 Торговый реестр МАРТ",
                _detail_records(
                    trade_records,
                    [
                        ("№", "registration_number"),
                        ("объект", "object_name"),
                        ("тип", "object_type"),
                        ("магазин", "internet_shop_domain"),
                        ("сеть", "trade_network_name"),
                        ("контакты", "object_contacts"),
                        ("включено", "inclusion_date"),
                    ],
                    limit=30,
                ),
            )
        )

    accreditation = profile.get("gias_accreditation") or {}
    if accreditation or locked_suppliers:
        gias_lines = []
        if accreditation:
            gias_lines.append("<b>Аккредитация</b>")
            gias_lines.extend(
                _detail_fields(
                    accreditation,
                    [
                        ("Статус", "state"),
                        ("Название", "summary"),
                        ("Телефон", "phone"),
                        ("Email", "email"),
                        ("Сайт", "web_site"),
                        ("Адрес", "placements_address"),
                        ("Действует с", "dt_from"),
                        ("Действует до", "dt_to"),
                    ],
                )
            )
        if locked_suppliers:
            gias_lines.append(f"\n<b>Недобросовестные поставщики ({len(locked_suppliers)})</b>")
            gias_lines.extend(
                _detail_records(
                    locked_suppliers,
                    [
                        ("статус", "state"),
                        ("№", "reg_number"),
                        ("включён", "add_date"),
                        ("исключён", "del_date"),
                        ("основание", "base_incl_text"),
                    ],
                )
            )
        messages.extend(_detail_messages("📑 ГИАС", gias_lines))

    if eaeu_records:
        messages.extend(
            _detail_messages(
                "🌍 ЕАЭС и свободные экономические зоны",
                _detail_records(
                    eaeu_records,
                    [
                        ("страна", "country"),
                        ("название", "full_name"),
                        ("СЭЗ", "sez_name"),
                        ("проект", "project_name"),
                        ("свидетельство", "certificate"),
                        ("дата", "registry_entry_date"),
                    ],
                ),
            )
        )

    if licenses:
        messages.extend(
            _detail_messages(
                "📜 Реестр лицензий",
                _detail_records(
                    licenses,
                    [
                        ("№", "generated_number"),
                        ("вид деятельности", "activity_type_name"),
                        ("с", "activity_date_start"),
                        ("по", "activity_date_end"),
                        ("активна", "activity_is_active"),
                    ],
                    limit=30,
                ),
            )
        )

    if inspections:
        messages.extend(
            _detail_messages(
                "🔎 Планы проверок",
                _detail_records(
                    inspections,
                    [
                        ("период", "plan_period"),
                        ("месяц", "start_month"),
                        ("орган", "controller_authority"),
                        ("регион", "source_region"),
                        ("план", "plan_title"),
                    ],
                    limit=30,
                ),
            )
        )

    if certificates:
        certificate_lines = _detail_records(
            certificates,
            [
                ("№", "cert_number"),
                ("бланк", "blank_number"),
                ("выдан", "issue_date"),
                ("действует до", "valid_until"),
                ("проверка", "verify_url"),
            ],
        )
        for index, certificate in enumerate(certificates[:20], start=1):
            products = certificate.get("products") or []
            if products:
                names = [_clean(item.get("name")) for item in products[:10]]
                certificate_lines.append(
                    f"Товары сертификата {index}: {escape(', '.join(name for name in names if name))}"
                )
        messages.extend(_detail_messages("🏅 Сертификаты БелТПП", certificate_lines))

    messages.append(
        "✅ <b>Подробный отчёт завершён</b>\n"
        "Обычные уведомления по подпискам остаются краткими. Новый полный отчёт формируется только по команде <code>/more</code>."
    )
    return messages


def company_keyboard(unp: int | str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "Открыть карточку", "callback_data": f"company:{unp}"}]
        ]
    }


def lookup_keyboard(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    buttons = []
    for item in results:
        unp = _clean(item.get("unp"))
        if not unp:
            continue
        buttons.append(
            [{"text": lookup_button_text(item), "callback_data": f"company:{unp}"}]
        )

    if not buttons:
        return None
    return {"inline_keyboard": buttons}
