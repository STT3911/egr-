"""Search normalization utilities for company names."""
import re
from typing import Optional


# ОПФ (организационно-правовые формы) для удаления из search_name
OPF_PATTERNS = [
    # Полные названия
    r'\bобщество\s+с\s+ограниченной\s+ответственностью\b',
    r'\bобщество\s+с\s+дополнительной\s+ответственностью\b',
    r'\bзакрытое\s+акционерное\s+общество\b',
    r'\bоткрытое\s+акционерное\s+общество\b',
    r'\bакционерное\s+общество\b',
    r'\bиндивидуальный\s+предприниматель\b',
    r'\bчастное\s+предприятие\b',
    r'\bчастное\s+унитарное\s+предприятие\b',
    r'\bчастное\s+торговое\s+унитарное\s+предприятие\b',
    r'\bчастное\s+производственно[\s\-]?торговое\s+предприятие\b',
    r'\bчастное\s+производственно[\s\-]?торговое\s+унитарное\s+предприятие\b',
    r'\bкоммунальное\s+унитарное\s+предприятие\b',
    r'\bреспубликанское\s+унитарное\s+предприятие\b',
    r'\bгосударственное\s+предприятие\b',
    r'\bгосударственное\s+учреждение\s+образования\b',
    r'\bрелигиозная\s+община\b',
    r'\bпроизводственный\s+кооператив\b',
    r'\bсельскохозяйственный\s+производственный\s+кооператив\b',
    r'\bкрестьянское\s+\(фермерское\)\s+хозяйство\b',
    r'\bобособленное\s+подразделение\b',
    r'\bфилиал\b',
    r'\bпредставительство\b',
    # Сокращения
    r'\bооо\b',
    r'\bодо\b',
    r'\bзао\b',
    r'\bоао\b',
    r'\bао\b',
    r'\bип\b',
    r'\bчуп\b',
    r'\bчпту\b',   # частное производственно-торговое унитарное
    r'\bкуп\b',
    r'\bруп\b',
    r'\bгп\b',
    r'\bпк\b',
    r'\bспк\b',
    r'\bк\s*\(\s*ф\s*\)\s*х\b',
    r'\bкфх\b',
    r'\bптуп\b',
    r'\bчптуп\b',
    r'\bзат\b',
    r'\bоат\b',
    # На беларусском
    r'\bтаварыства\s+з\s+абмежаванай\s+адказнасцю\b',
    r'\bтаа\b',
    # Дополнительные
    r'\bltd\b',
    r'\bllc\b',
    r'\binc\b',
    r'\bcorp\b',
    r'\blimited\b',
]

# Символы для удаления (кроме букв, цифр и пробелов)
SPECIAL_CHARS_PATTERN = r'[^\w\s]'

# Множественные пробелы
MULTIPLE_SPACES_PATTERN = r'\s+'


def normalize_company_name(name: Optional[str]) -> Optional[str]:
    """
    Нормализует название компании для поиска.
    
    Шаги:
    1. Приведение к нижнему регистру
    2. Удаление ОПФ
    3. Удаление спецсимволов (кавычки, дефисы и т.п.)
    4. Удаление множественных пробелов
    5. Trim
    
    Примеры:
        'Общество с ограниченной ответственностью "КулЭирТех"' -> 'кулэиртех'
        'ООО "Рога и Копыта"' -> 'рога и копыта'
        'ИП Иванов И.И.' -> 'иванов и и'
        'ЗАО "Минск-Кристалл"' -> 'минск кристалл'
    """
    if not name:
        return None
    
    # 1. Нижний регистр
    result = name.lower().strip()
    
    # 2. Удаление ОПФ
    for pattern in OPF_PATTERNS:
        result = re.sub(pattern, ' ', result, flags=re.IGNORECASE)
    
    # 3. Удаление спецсимволов (оставляем только буквы, цифры, пробелы)
    result = re.sub(SPECIAL_CHARS_PATTERN, ' ', result)
    
    # 4. Замена множественных пробелов на один
    result = re.sub(MULTIPLE_SPACES_PATTERN, ' ', result)
    
    # 5. Trim и проверка на пустоту
    result = result.strip()
    
    return result if result else None


def is_similar_search_term(search_term: str, normalized_name: str, threshold: float = 0.8) -> bool:
    """
    Проверяет схожесть поискового запроса с нормализованным названием.
    
    Для более продвинутого поиска можно использовать:
    - pg_trgm (PostgreSQL trigram similarity)
    - Levenshtein distance
    - FTS (Full Text Search)
    """
    # Простая проверка на вхождение
    search_normalized = normalize_company_name(search_term)
    if not search_normalized:
        return False
    
    # Проверяем вхождение каждого слова
    search_words = set(search_normalized.split())
    name_words = set(normalized_name.split())
    
    # Если все слова из запроса есть в названии - совпадение
    return search_words.issubset(name_words)


# --- Транслитерация латиница <-> кириллица --------------------------------
# Используем для поиска: "minsk" должен находить "минск" и наоборот.
# Порядок важен: многобуквенные сочетания идут раньше однобуквенных.

# Латиница -> кириллица (для запросов на латинице)
_LAT_TO_CYR = [
    ("shch", "щ"), ("sch", "щ"),
    ("yo", "ё"), ("zh", "ж"), ("kh", "х"), ("ts", "ц"), ("ch", "ч"),
    ("sh", "ш"), ("yu", "ю"), ("ya", "я"), ("ye", "е"), ("yi", "и"),
    ("iy", "ий"), ("ij", "ий"),
    ("a", "а"), ("b", "б"), ("v", "в"), ("g", "г"), ("d", "д"),
    ("e", "е"), ("z", "з"), ("i", "и"), ("j", "й"), ("k", "к"),
    ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"),
    ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"), ("f", "ф"),
    ("h", "х"), ("c", "ц"), ("y", "ы"), ("w", "в"), ("x", "кс"),
    ("'", ""), ("`", ""),
]

# Кириллица -> латиница (для запросов на кириллице)
_CYR_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    # Беларускія літары
    "і": "i", "ў": "u",
}

_HAS_CYRILLIC = re.compile(r"[а-яёіў]")
_HAS_LATIN = re.compile(r"[a-z]")


def transliterate_lat_to_cyr(text: str) -> str:
    """Грубая транслитерация латиницы в кириллицу (для поиска)."""
    result = text.lower()
    for lat, cyr in _LAT_TO_CYR:
        result = result.replace(lat, cyr)
    return result


def transliterate_cyr_to_lat(text: str) -> str:
    """Грубая транслитерация кириллицы в латиницу (для поиска)."""
    return "".join(_CYR_TO_LAT.get(ch, ch) for ch in text.lower())


def transliterate_query(query: Optional[str]) -> Optional[str]:
    """
    Подобрать транслитерированный вариант запроса:
    - есть латиница (и нет кириллицы) -> переводим в кириллицу;
    - есть кириллица -> переводим в латиницу.
    Возвращает None, если вариант совпадает с исходным или пуст.
    """
    if not query:
        return None
    q = query.lower().strip()
    if not q:
        return None
    if _HAS_LATIN.search(q) and not _HAS_CYRILLIC.search(q):
        variant = transliterate_lat_to_cyr(q)
    elif _HAS_CYRILLIC.search(q):
        variant = transliterate_cyr_to_lat(q)
    else:
        return None
    variant = variant.strip()
    return variant if variant and variant != q else None


def generate_search_variants(name: Optional[str]) -> list[str]:
    """
    Генерирует варианты запроса для поиска:
    - нормализованное название (без ОПФ/спецсимволов);
    - без пробелов;
    - транслитерированный вариант (лат<->кир) и его нормализация.
    """
    variants: list[str] = []

    def _add(value: Optional[str]) -> None:
        if value:
            v = value.strip()
            if v and v not in variants:
                variants.append(v)

    if name:
        normalized = normalize_company_name(name)
        _add(normalized)
        if normalized:
            _add(normalized.replace(" ", ""))

        translit = transliterate_query(name)
        _add(translit)
        if translit:
            _add(normalize_company_name(translit))

    return variants


# Примеры для тестирования
if __name__ == '__main__':
    test_cases = [
        'Общество с ограниченной ответственностью "КулЭирТех"',
        'ООО "Рога и Копыта"',
        'ИП Иванов Иван Иванович',
        'ЗАО "Минск-Кристалл"',
        'ОДО "СтройМаркет-Плюс"',
        'Частное унитарное предприятие "Техносервис"',
        'ОАО "Беларуськалий"',
    ]
    
    print("Примеры нормализации:\n")
    for case in test_cases:
        normalized = normalize_company_name(case)
        print(f"'{case}'")
        print(f"  -> '{normalized}'\n")
