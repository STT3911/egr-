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
    "/mysubs — мои подписки"
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
