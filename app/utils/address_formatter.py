"""Address formatting utilities for GRP taxpayer data."""

import re
from typing import Optional


def format_grp_address(address: Optional[str]) -> Optional[str]:
    """
    Форматирует адрес из ГРП для более читабельного вида.

    Добавляет пробелы после сокращений и убирает лишние запятые.

    Примеры:
        'г.Минск,ул.Карбышева,11,кв.108' -> 'г. Минск, ул. Карбышева 11, кв. 108'
        'г.Минск,ул.Ленина,д.5,кв.10' -> 'г. Минск, ул. Ленина д. 5, кв. 10'
    """
    if not address:
        return address

    # Сначала разделяем по запятым и обрабатываем каждую часть
    parts = [part.strip() for part in address.split(',') if part.strip()]

    formatted_parts = []
    for part in parts:
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
        None,
        '',
        'г.Минск',
    ]

    print("Тесты форматирования адресов:\n")
    for case in test_cases:
        result = format_grp_address(case)
        print(f"'{case}'")
        print(f"  -> '{result}'\n")