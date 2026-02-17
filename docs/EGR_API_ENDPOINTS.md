# Эндпоинты ЕГР, к которым обращается сервис

Базовые URL задаются в `.env`:
- **EGR_API_URL** = `https://egr.gov.by/api/v2/egr` (основной API)
- **EGR_MOBILE_API_URL** = `https://egr.gov.by/egrmobile/api/v1` (мобильный API)

---

## 1. Основной API (EGR_API_URL)

Все запросы: **GET**. Даты в формате **DD.MM.YYYY**.

| Метод в коде | URL эндпоинта | Где используется |
|--------------|----------------|-------------------|
| `get_base_info_by_period` | `getBaseInfoByPeriod/{start_date}/{end_date}` | Загрузка по периоду, синк дневных изменений |
| `get_events_by_period` | `getEventByPeriod/{start_date}/{end_date}` | Загрузка событий по периоду |
| `get_base_info` | `getBaseInfoByRegNum/{unp}` | Полная история компании (внутри get_full_company_history) |
| `get_all_addresses` | `getAllAddressByRegNum/{unp}` | Полная история компании |
| `get_all_ved` | `getAllVEDByRegNum/{unp}` | Полная история компании |
| `get_all_jur_names` | `getAllJurNamesByRegNum/{unp}` | Полная история (ЮЛ) |
| `get_all_ip_fio` | `getAllIPFIOByRegNum/{unp}` | Полная история (ИП) |

**Один «полный» запрос по УНП** = 1 вызов `getBaseInfoByRegNum` + 1 `getAllAddressByRegNum` + 1 `getAllVEDByRegNum` + 1 `getAllJurNamesByRegNum` **или** `getAllIPFIOByRegNum` (всего 4 запроса на УНП).

Эндпоинты ниже в коде есть, но **в фоновых задачах и синке не вызываются** (только при необходимости в API/ручных сценариях):

| Метод в коде | URL эндпоинта |
|--------------|----------------|
| `get_address` | `getAddressByRegNum/{unp}` |
| `get_jur_name` | `getJurNamesByRegNum/{unp}` |
| `get_ved_current` | `getVEDByRegNum/{unp}` |
| `get_ip_fio_current` | `getIPFIOByRegNum/{unp}` |
| `get_events` | `getEventByRegNum/{unp}` |
| `get_short_info_by_name` | `getShortInfoByRegName/{name}` |
| `get_short_info` | `getShortInfoByRegNum/{unp}` |
| `get_reg_nums_by_state` | `getRegNumByState/{state}` |
| `get_addresses_by_period` | `getAddressByPeriod/{start}/{end}` |
| `get_jur_names_by_period` | `getJurNamesByPeriod/{start}/{end}` |
| `get_ved_by_period` | `getVEDByPeriod/{start}/{end}` |
| `get_ip_fio_by_period` | `getIPFIOByPeriod/{start}/{end}` |
| `get_short_info_by_period` | `getShortInfoByPeriod/{start}/{end}` |

---

## 2. Мобильный API (EGR_MOBILE_API_URL)

Используется в API сервиса для эндпоинтов «сырые данные» и «сравнение API».

| Метод в коде | URL | Параметры |
|--------------|-----|-----------|
| `get_common_info` | `extracts/commonInfo` | `pan=...` (9 цифр) или `unn=...` |
| `get_place_location` | `extracts/placeLocation` | `unn=...` или `pan=...` |

---

## Итого: что реально дергается при синке и загрузке

- **По периоду:**  
  `getBaseInfoByPeriod/{start}/{end}`,  
  `getEventByPeriod/{start}/{end}`.

- **По одному УНП (полная история в raw):**  
  `getBaseInfoByRegNum/{unp}`,  
  `getAllAddressByRegNum/{unp}`,  
  `getAllVEDByRegNum/{unp}`,  
  `getAllJurNamesByRegNum/{unp}` **или** `getAllIPFIOByRegNum/{unp}`.

Остальные эндпоинты из таблиц выше — по необходимости (ручной вызов, сравнение API, сырые данные в REST).
