import re
from typing import List, Dict, Any


def normalize_search_text(text: str) -> str:
    """
    Нормализация текста для поиска согласно ТЗ.
    """
    if not text:
        return ""

    # Замена ё на е
    text = text.replace('ё', 'е').replace('Ё', 'Е')

    # Приведение к нижнему регистру
    text = text.lower()

    # Замена дефисов на подчёркивания
    text = text.replace('-', '_')

    # Удаление специальных символов
    for char in ':!?\'()"«»;,.':
        text = text.replace(char, ' ')

    # Замена нескольких пробелов одним
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def convert_timestamp(ts: int) -> str:
    """
    Конвертировать timestamp в строку даты.
    """
    from datetime import datetime
    if ts:
        return datetime.fromtimestamp(ts / 1000).isoformat()
    return None