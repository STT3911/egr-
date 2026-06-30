"""Разбор сырого поля контактов на телефоны / email / прочее.

Источники (МАРТ object_contacts, ЕГР phone/email и т.п.) дают свободный текст:
в одной строке вперемешку телефоны, email и прочее (домены). Форматы телефонов
разные: слитные (`+375296197299`, МАРТ) и с пробелами-форматированием
(`+37517 233 58 95`, ЕГР), с кодом и без, через `+`/`80`/`375`.

Стратегия:
  1) вынуть e-mail (иначе цифры из них примут за телефон);
  2) остаток порезать на сегменты по `,` `;` (надёжные разделители);
  3) в сегменте: если есть `+` — каждый `+…` отдельный номер; иначе сегмент с
     пробелами это ОДИН номер (форматирование) при ≤13 цифрах, либо несколько
     (делим по пробелам) при большем числе цифр;
  4) что не телефон и содержит буквы (домен/слово) → other; мусор-обрывки цифр — отбрасываем.

Функция чистая (без БД) — используется в API и сборщике, легко тестируется.
"""
from __future__ import annotations

import re

# Неякорный поиск e-mail внутри строки (для извлечения из смеси).
_EMAIL_FIND_RE = re.compile(
    r"[A-Za-z0-9_%+\-]+(?:\.[A-Za-z0-9_%+\-]+)*"
    r"@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}"
)
_LETTER_RE = re.compile(r"[A-Za-zА-Яа-я]")


def _normalize_phone(cand: str) -> str | None:
    """Кандидат → нормализованный телефон (+375…) или None, если не похоже на номер."""
    digits = re.sub(r"\D", "", cand)
    if not (6 <= len(digits) <= 13):
        return None
    if cand.lstrip().startswith("+"):
        return "+" + digits
    if digits.startswith("375"):
        return "+" + digits
    if digits.startswith("80") and len(digits) >= 11:   # белорусский выход 80<код> → +375<код>
        return "+375" + digits[2:]
    return digits                                        # местный номер без кода страны


def parse_contacts(raw: str | None) -> dict[str, list[str]]:
    """Разобрать строку контактов на {'phones': [...], 'emails': [...], 'other': [...]}.

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

    text = str(raw)

    # 1) e-mail — вынимаем и убираем из текста
    for email in _EMAIL_FIND_RE.findall(text):
        add("emails", email.lower())
    text = _EMAIL_FIND_RE.sub(" ", text)

    # 2) сегменты по , ;
    for seg in re.split(r"[;,]", text):
        seg = seg.strip()
        if not seg:
            continue

        if "+" in seg:
            candidates = [c for c in re.split(r"(?=\+)", seg) if c.strip()]
        else:
            digits = re.sub(r"\D", "", seg)
            candidates = [seg] if len(digits) <= 13 else seg.split()

        for cand in candidates:
            cand = cand.strip()
            if not cand:
                continue
            phone = _normalize_phone(cand)
            if phone:
                add("phones", phone)
            elif _LETTER_RE.search(cand):
                add("other", cand)        # домен/слово (напр. optik.by) — в прочее
            # иначе мусорный обрывок цифр — отбрасываем

    return result
