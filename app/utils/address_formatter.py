"""Address formatting utilities for GRP taxpayer data."""

import re
from typing import Optional


def format_grp_address(address: Optional[str]) -> Optional[str]:
    """
    Форматирует адрес из ГРП для более читабельного вида.

    Добавляет пробелы после сокращений, убирает лишние запятые,
    удаляет страну и район из адреса.

    Примеры:
        'г.Минск,ул.Карбышева,11,кв.108' -> 'г. Минск, ул. Карбышева 11, кв. 108'
        'г.Минск,ул.Ленина,д.5,кв.10' -> 'г. Минск, ул. Ленина д. 5, кв. 10'
        'Республика Беларусь, Минский район, г.Минск, ул.Карбышева 11' -> 'г. Минск, ул. Карбышева 11'
    """
    if not address:
        return address

    # Сначала разделяем по запятым и обрабатываем каждую часть
    parts = [part.strip() for part in address.split(',') if part.strip()]

    # Фильтруем части адреса - удаляем страну и район
    filtered_parts = []
    for part in parts:
        part_clean = part.strip()

        # Пропускаем части содержащие страну
        if any(country in part_clean for country in [
            'Республика Беларусь', 'Беларусь', 'РБ', 'Республика',
            'Р РµСЃРїСѓР±Р»РёРєР° Р‘РµР»Р°СЂСѓСЃСЊ', 'Р‘РµР»Р°СЂСѓСЃСЊ', 'Р РµСЃРїСѓР±Р»РёРєР°'
        ]):
            continue

        # Пропускаем части содержащие район (если это не часть города)
        if any(district in part_clean for district in ['район', 'р-н', 'р.', 'СЂР°Р№РѕРЅ', 'СЂ-РЅ', 'СЂ.']) and 'г.' not in part_clean:
            continue

        filtered_parts.append(part)

    formatted_parts = []
    for part in filtered_parts:
        # Добавляем пробел после сокращений
        formatted_part = re.sub(r'\b(г|ул|пр-т|пр|пер|пл|кв|д|оф|корп)\.', r'\1. ', part)
        # Убираем множественные пробелы
        formatted_part = re.sub(r'\s+', ' ', formatted_part)
        formatted_parts.append(formatted_part.strip())

    # Соединяем обратно с запятыми и пробелами
    result = ', '.join(formatted_parts)

    # Финальная очистка множественных пробелов
    result = re.sub(r'\s+', ' ', result)

    return result.strip()


# Тесты
if __name__ == '__main__':
    test_cases = [
        'г.Минск,ул.Карбышева,11,кв.108',
        'г.Минск,ул.Ленина,д.5,кв.10',
        'г.Гродно,пр-т.Космонавтов,15,оф.5',
        'г.Брест,ул.Гоголя,д.22,корп.3,кв.45',
        'Республика Беларусь, Минский район, г.Минск, ул.Карбышева 11',
        'Беларусь, Гродненский р-н, г.Гродно, ул.Ленина 5',
        'Минский район, г.Минск, ул.Независимости 10',
        None,
        '',
        'г.Минск',
    ]

    print("Тесты форматирования адресов:\n")
    for case in test_cases:
        result = format_grp_address(case)
        print(f"Input: {case}")
        print(f"Output: {result}")
        print("---")