"""Address normalization for company matching and exact-unit risk checks.

ЕГР-адреса включают квартиру/офис, поэтому две компании в одном доме, но в разных
кабинетах, текстуально не совпадают. Нормализация отрезает квартиру/офис/помещение
и убирает подписи компонентов (г./ул./д. и т.п.), которые то пишут, то нет —
остаётся сравнимый "адрес здания".

Эвристика, не полноценный парсер адресов. Цель — сгруппировать заведомо совпадающие
дома, а не разобрать адрес полностью. Ложноотрицательные результаты (не нашли
совпадение из-за опечатки/иного порядка слов) — приемлемы, ложноположительные
(ошибочно объединили разные дома) — недопустимы, поэтому при недостатке текста
после очистки функция лучше вернёт None, чем рискованный короткий ключ.
"""
from __future__ import annotations

import re

_COUNTRY_RE = re.compile(r"республика\s+беларусь|^\s*беларусь\b", re.IGNORECASE)

# Квартира/офис/помещение — как правило последний компонент адреса (после запятой).
# Как только встретили — обрезаем этот и все последующие компоненты.
_UNIT_MARKER_RE = re.compile(
    r"\b(кв|квартира|оф|офис|пом|помещение|ком|комн|каб|кабинет)\.?\s*№?\s*\d",
    re.IGNORECASE,
)

_UNIT_LABELS = (
    (re.compile(r"\b(?:квартира|кв)\.?\s*№?\s*", re.IGNORECASE), "кв "),
    (re.compile(r"\b(?:офис|оф)\.?\s*№?\s*", re.IGNORECASE), "оф "),
    (re.compile(r"\b(?:помещение|пом)\.?\s*№?\s*", re.IGNORECASE), "пом "),
    (re.compile(r"\b(?:комната|комн|ком)\.?\s*№?\s*", re.IGNORECASE), "ком "),
    (re.compile(r"\b(?:кабинет|каб)\.?\s*№?\s*", re.IGNORECASE), "каб "),
)

# Подписи компонентов адреса: сами по себе не различают адреса (то есть, то нет),
# различается только значение после них — поэтому подпись убираем, значение оставляем.
# \b...\b — целое слово, чтобы не покорёжить названия вроде "Гродно"/"Грушевая"/"Гомель".
_LABEL_RE = re.compile(
    r"\b(?:г|город|гор|обл|область|р-н|район|ул|улица|пр-т|проспект|пр|пер|переулок|"
    r"пл|площадь|б-р|бульвар|д|дом|корп|корпус|стр|строение)\b\.?\s*",
    re.IGNORECASE,
)

_NON_ALNUM_RE = re.compile(r"[^a-zа-яё0-9]+")

MIN_KEY_LENGTH = 6


def building_address_key(full_address: str | None) -> str | None:
    """Нормализованный ключ адреса ЗДАНИЯ (без квартиры/офиса) для группировки.

    None, если адреса нет или после очистки осталось слишком мало текста, чтобы
    безопасно на нём матчить.
    """
    if not full_address:
        return None

    text = full_address.replace("\xa0", " ")
    text = _COUNTRY_RE.sub("", text)

    parts = [p.strip() for p in text.split(",") if p.strip()]
    kept: list[str] = []
    for part in parts:
        if _UNIT_MARKER_RE.search(part):
            break
        kept.append(part)

    cleaned = " ".join(kept).lower()
    cleaned = _LABEL_RE.sub(" ", cleaned)
    cleaned = _NON_ALNUM_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if len(cleaned) < MIN_KEY_LENGTH:
        return None
    return cleaned


def unit_address_key(full_address: str | None) -> str | None:
    """Return a normalized *full* address only when a unit is explicitly present.

    A building by itself is intentionally not enough for a risk match: several
    unrelated companies can normally occupy different offices in one building.
    Apartment/office/premise labels remain part of the key so, for example,
    ``кв. 12`` and ``оф. 12`` do not become the same address.
    """
    if not full_address or not _UNIT_MARKER_RE.search(full_address):
        return None

    text = full_address.replace("\xa0", " ")
    text = _COUNTRY_RE.sub("", text)
    for pattern, replacement in _UNIT_LABELS:
        text = pattern.sub(replacement, text)

    cleaned = text.lower()
    cleaned = _LABEL_RE.sub(" ", cleaned)
    cleaned = _NON_ALNUM_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if len(cleaned) < MIN_KEY_LENGTH:
        return None
    return cleaned
