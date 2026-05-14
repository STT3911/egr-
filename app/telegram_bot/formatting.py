"""Message formatting helpers for the Telegram bot."""
from __future__ import annotations

from html import escape
from typing import Any


HELP_TEXT = (
    "Напишите УНП или часть названия компании.\n\n"
    "Примеры:\n"
    "500000306\n"
    "минский автомобильный"
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

    address = _clean(company.get("place_location_address"))
    if not address:
        for item in company.get("addresses") or []:
            address = _clean(item.get("full_address"))
            if address:
                break
    if address:
        lines.append(f"Адрес: {escape(address)}")

    for item in company.get("ved") or []:
        ved_code = _clean(item.get("ved_code"))
        ved_name = _clean(item.get("ved_name"))
        if ved_code or ved_name:
            value = " ".join(part for part in [ved_code, ved_name] if part)
            lines.append(f"ВЭД: {escape(value)}")
            break

    contact_lines = []
    for item in company.get("contacts") or []:
        email = _clean(item.get("email"))
        website = _clean(item.get("website"))
        phone = _clean(item.get("phone"))
        if email:
            contact_lines.append(f"Email: {escape(email)}")
        if website:
            contact_lines.append(f"Сайт: {escape(website)}")
        if phone:
            contact_lines.append(f"Телефон: {escape(phone)}")
        if contact_lines:
            break
    lines.extend(contact_lines)

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
