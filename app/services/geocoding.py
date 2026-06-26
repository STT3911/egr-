"""
Геокодинг адресов через OpenStreetMap/Nominatim.

Почему OSM, а не Яндекс: бесплатная лицензия Яндекс-геокодера запрещает хранить
результаты в БД и требует показывать их только на карте Яндекса. Nominatim
(данные OSM, лицензия ODbL) разрешает кэшировать/хранить координаты при указании
авторства. Поэтому координаты в `egr_company_place_locations` берём из OSM, а на
карточке их рисует уже Яндекс-карта по готовым координатам (это лицензию не нарушает).

Ключевое по качеству: свободный текст ("г. Минск, ул. ..., д. 15, оф. 408") с
сокращениями Nominatim разбирает плохо — цепляется за номер дома и возвращает
случайные точки в сельсоветах. Поэтому адрес парсится на город/улицу/дом и шлётся
СТРУКТУРИРОВАННЫМ запросом (street/city), а результат отсекается по place_rank
(ниже уровня улицы — это промах).

Ограничения Nominatim (публичный инстанс):
  * не более 1 запроса в секунду — соблюдается на стороне вызывающего кода;
  * обязателен валидный User-Agent с контактом (settings.NOMINATIM_USER_AGENT);
  * один вызов = один HTTP-запрос (без внутренних ретраев), чтобы не нарушать лимит.
"""

import re
from typing import Optional, Tuple, Dict

import httpx

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("geocoding")

# Минимальный place_rank валидного попадания: 26 = улица, 30 = дом/здание.
# Ниже (населённый пункт / участок / регион) — это промах геокодера, отбрасываем.
_MIN_PLACE_RANK = 26

# Город/населённый пункт. Имя не должно начинаться с цифры — иначе "д. 15" (дом)
# спутается с "д. Околица" (деревня).
_CITY_RE = re.compile(
    r"^(?:г|гор|город|г\.?\s*п|городской\s+посёлок|аг|агрогородок|пос|посёлок|поселок|"
    r"гп|кп|рп|д|деревня|с|село)\.?\s*(?P<name>[^\d].*)$",
    re.IGNORECASE,
)
# Улица/проспект/переулок и т.п. ("пр-т" раньше "пр" в альтернации).
_STREET_RE = re.compile(
    r"^(?:ул|улица|пр-т|пр-кт|просп|проспект|пр|пер|переулок|б-р|бул|бульвар|пл|площадь|"
    r"ш|шоссе|наб|набережная|проезд|тракт|мкр|микрорайон|туп|тупик)\.?\s*(?P<name>.+)$",
    re.IGNORECASE,
)
# Дом: "д. 15", "дом 15", "д.15А", "15/2".
_HOUSE_RE = re.compile(
    r"^(?:д|дом|зд|здание)\.?\s*(?P<num>\d+[а-яёa-z]?(?:[/-]\d+[а-яёa-z]?)?)$",
    re.IGNORECASE,
)
_BARE_HOUSE_RE = re.compile(r"^\d+[а-яёА-ЯЁa-zA-Z]?(?:[/-]\d+[а-яёА-ЯЁa-zA-Z]?)?$")
# Офис/квартира/этаж/корпус и т.п. — выкидываем (Nominatim их не знает).
_DROP_RE = re.compile(
    r"^(?:оф|офис|кв|квартира|пом|помещение|каб|кабинет|комн|комната|эт|этаж|"
    r"к|корп|корпус|стр|строение|подъезд)\.?\s*\d",
    re.IGNORECASE,
)


def build_query(address: str) -> str:
    """Свободный текст для геокодера: добавляет страну, если её нет (фолбэк)."""
    addr = (address or "").strip()
    if not addr:
        return addr
    if re.search(r"беларус", addr, re.IGNORECASE):
        return addr
    return f"Беларусь, {addr}"


def parse_address(address: str) -> Dict[str, Optional[str]]:
    """
    Разбирает белорусский адрес ЕГР/ГРП на город/улицу/дом для структурированного
    запроса Nominatim. Сокращения и офис/квартиру выкидываем.

    Пример: 'г. Минск, ул. Франциска Скорины, д. 15, оф. 408'
            -> {'city': 'Минск', 'street': 'Франциска Скорины', 'house': '15'}
    """
    city = street = house = None
    for raw in (address or "").split(","):
        part = raw.strip()
        if not part:
            continue

        if city is None:
            m = _CITY_RE.match(part)
            if m:
                city = m.group("name").strip()
                continue

        if _DROP_RE.match(part):  # офис/квартира/этаж — пропускаем
            continue

        if street is None:
            m = _STREET_RE.match(part)
            if m:
                street = m.group("name").strip()
                continue

        if house is None:
            m = _HOUSE_RE.match(part)
            if m:
                house = m.group("num").strip()
                continue
            # Голый номер дома засчитываем только если улицу уже нашли.
            if street is not None and _BARE_HOUSE_RE.match(part):
                house = part.strip()
                continue
        # район и всё остальное игнорируем

    return {"city": city, "street": street, "house": house}


async def geocode_address_yandex(http: httpx.AsyncClient, address: str) -> Optional[Tuple[float, float]]:
    """
    Геокодит адрес через Яндекс HTTP-геокодер (точное покрытие по РБ, в отличие
    от OSM). Возвращает (lat, lon) или None.

    Требует settings.YANDEX_GEOCODER_API_KEY (ключ «API Геокодера», тот же, что в
    Postman: geocode-maps.yandex.ru/1.x). Делает один HTTP-запрос.

    ВНИМАНИЕ по лицензии: бесплатный тариф запрещает хранить результаты и требует
    показывать их на карте Яндекса. Кэширование в БД — осознанный компромисс ради
    лимита 1k/сутки (решение на стороне продукта).
    """
    addr = (address or "").strip()
    if not addr:
        return None

    key = settings.YANDEX_GEOCODER_API_KEY
    if not key:
        logger.warning("YANDEX_GEOCODER_API_KEY не задан — геокодинг отключён")
        return None

    params = {
        "apikey": key,
        "geocode": build_query(addr),
        "format": "json",
        "results": 1,
        "lang": "ru_RU",
    }
    resp = await http.get(settings.YANDEX_GEOCODER_URL, params=params)
    resp.raise_for_status()
    data = resp.json()

    try:
        members = data["response"]["GeoObjectCollection"]["featureMember"]
        if not members:
            return None
        # Яндекс отдаёт Point.pos как "долгота широта" — порядок обратный нашему.
        pos = members[0]["GeoObject"]["Point"]["pos"]
        lon_str, lat_str = pos.split()
        return float(lat_str), float(lon_str)
    except (KeyError, ValueError, IndexError, TypeError):
        logger.warning("Yandex geocoder: неожиданный ответ для %r", addr)
        return None


async def geocode_address(http: httpx.AsyncClient, address: str) -> Optional[Tuple[float, float]]:
    """
    Возвращает (lat, lon) для адреса или None, если ничего достоверного не найдено.

    `http` — переиспользуемый httpx.AsyncClient с заголовком User-Agent.
    Делает РОВНО один HTTP-запрос (структурированный, если удалось распарсить
    улицу/город; иначе свободный текст), чтобы не нарушать лимит Nominatim 1 req/sec.
    """
    if not (address or "").strip():
        return None

    params = {"format": "jsonv2", "limit": 1, "addressdetails": 0}
    if settings.NOMINATIM_COUNTRY_CODES:
        params["countrycodes"] = settings.NOMINATIM_COUNTRY_CODES

    parsed = parse_address(address)
    if parsed["street"] or parsed["city"]:
        if parsed["street"]:
            params["street"] = (
                f'{parsed["street"]} {parsed["house"]}'.strip()
                if parsed["house"]
                else parsed["street"]
            )
        if parsed["city"]:
            params["city"] = parsed["city"]
    else:
        params["q"] = build_query(address)

    resp = await http.get(f"{settings.NOMINATIM_BASE_URL}/search", params=params)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return None

    item = data[0]
    # Отсекаем промахи уровня населённого пункта/участка/региона.
    rank = item.get("place_rank")
    try:
        if rank is not None and int(rank) < _MIN_PLACE_RANK:
            logger.info("Nominatim: низкий place_rank=%s для %r — пропускаем", rank, address)
            return None
        lat = float(item["lat"])
        lon = float(item["lon"])
    except (KeyError, ValueError, TypeError):
        logger.warning("Nominatim: неожиданный формат ответа для %r", address)
        return None

    return lat, lon
