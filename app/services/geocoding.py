"""
Геокодинг адресов через OpenStreetMap/Nominatim.

Почему OSM, а не Яндекс: бесплатная лицензия Яндекс-геокодера запрещает хранить
результаты в БД и требует показывать их только на карте Яндекса. Nominatim
(данные OSM, лицензия ODbL) разрешает кэшировать/хранить координаты при указании
авторства. Поэтому координаты в `egr_company_place_locations` берём из OSM, а на
карточке их рисует уже Яндекс-карта по готовым координатам (это лицензию не нарушает).

Ограничения Nominatim (публичный инстанс):
  * не более 1 запроса в секунду — соблюдается на стороне вызывающей задачи;
  * обязателен валидный User-Agent с контактом (settings.NOMINATIM_USER_AGENT).
"""

import re
from typing import Optional, Tuple

import httpx

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("geocoding")


def build_query(address: str) -> str:
    """Готовит адрес для геокодера: добавляет страну, если её нет."""
    addr = (address or "").strip()
    if not addr:
        return addr
    if re.search(r"беларус", addr, re.IGNORECASE):
        return addr
    return f"Беларусь, {addr}"


async def geocode_address(http: httpx.AsyncClient, address: str) -> Optional[Tuple[float, float]]:
    """
    Возвращает (lat, lon) для адреса или None, если ничего не найдено.

    `http` — переиспользуемый httpx.AsyncClient с заголовком User-Agent.
    Соблюдение лимита 1 req/sec — забота вызывающего кода (пауза между вызовами).
    """
    query = build_query(address)
    if not query:
        return None

    params = {
        "q": query,
        "format": "jsonv2",
        "limit": 1,
        "addressdetails": 0,
    }
    if settings.NOMINATIM_COUNTRY_CODES:
        params["countrycodes"] = settings.NOMINATIM_COUNTRY_CODES

    resp = await http.get(f"{settings.NOMINATIM_BASE_URL}/search", params=params)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return None

    try:
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
    except (KeyError, ValueError, TypeError):
        logger.warning("Nominatim: неожиданный формат ответа для %r", query)
        return None

    return lat, lon
