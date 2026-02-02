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


def generate_search_variants(name: Optional[str]) -> list[str]:
    """
    Генерирует варианты для поиска (для будущего расширения).
    
    Может включать:
    - Транслитерацию (лат <-> кир)
    - Синонимы
    - Аббревиатуры
    """
    variants = []
    
    if name:
        normalized = normalize_company_name(name)
        if normalized:
            variants.append(normalized)
            
            # Можно добавить варианты без пробелов
            variants.append(normalized.replace(' ', ''))
    
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
