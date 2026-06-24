"""Разбор сырого поля контактов МАРТ (`object_contacts`) на телефоны / email / прочее.

В торговом реестре МАРТ контакты — свободный текст: в одной ячейке вперемешку
телефоны (`+375..`, `375..`, `80..`), email и прочее (домены, напр. `optik.by`).
Бьём по пробелам/запятым/точкам-с-запятой и классифицируем каждый токен.

Функция чистая (без БД) — используется при отдаче компании в API и легко тестируется.
"""
from __future__ import annotations

import re

# Разделители между контактами: пробелы, запятые, точки с запятой.
# Точку НЕ включаем — иначе порвём домены/email (optik.by, a@b.by).
_SPLIT_RE = re.compile(r"[\s,;]+")

_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9_%+\-]+(?:\.[A-Za-z0-9_%+\-]+)*"   # локальная часть
    r"@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*"          # домен
    r"\.[A-Za-z]{2,}$"                                # TLD
)

# Токен-телефон: только телефонные символы (цифры, + - ( )).
_PHONE_TOKEN_RE = re.compile(r"^[+(]?[\d()\-+]+$")


def _normalize_phone(token: str) -> str:
    """Привести номер к +375…, где это однозначно (РБ). Иначе — только цифры."""
    digits = re.sub(r"\D", "", token)
    if token.lstrip().startswith("+"):
        return "+" + digits
    if digits.startswith("375"):
        return "+" + digits
    if digits.startswith("80"):          # белорусский выход 80<код> → +375<код>
        return "+375" + digits[2:]
    return digits                        # местный номер без кода страны — как есть


def parse_contacts(raw: str | None) -> dict[str, list[str]]:
    """Разобрать `object_contacts` на {'phones': [...], 'emails': [...], 'other': [...]}.

    Каждая категория дедуплицируется (без учёта регистра), порядок появления сохраняется.
    """
    result: dict[str, list[str]] = {"phones": [], "emails": [], "other": []}
    if not raw:
        return result
    seen: dict[str, set[str]] = {"phones": set(), "emails": set(), "other": set()}

    def add(kind: str, value: str) -> None:
        key = value.lower()
        if key not in seen[kind]:
            seen[kind].add(key)
            result[kind].append(value)

    for token in _SPLIT_RE.split(str(raw).strip()):
        token = token.strip().strip(".,;")
        if not token:
            continue

        if "@" in token:
            # есть собака → это попытка email; валидный кладём в emails, кривой — в other
            if _EMAIL_RE.match(token):
                add("emails", token.lower())
            else:
                add("other", token)
            continue

        digits = re.sub(r"\D", "", token)
        if len(digits) >= 6 and _PHONE_TOKEN_RE.match(token):
            add("phones", _normalize_phone(token))
        else:
            add("other", token)

    return result
