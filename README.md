# ЕГР Aggregator Service

Микросервис для агрегации данных из API ЕГР Республики Беларусь.

## Возможности

- 🔄 Автоматическая синхронизация данных из ЕГР
- 📊 Поддержка двух API: Mobile (быстрый) и Legacy (полный)
- 💾 Буферизация сырых данных (ELT паттерн)
- 📜 История изменений компаний (названия, адреса, ВЭД, контакты)
- 📋 История событий (регистрация, ликвидация, банкротство)
- 📚 18 справочников NSI из ЕГР
- 🔍 REST API для поиска компаний
- 🎯 Поиск по названию и фильтрация по статусу
- ⚡ Фоновая обработка через Celery
- 🐳 Docker-ready

## Статистика реализации

- ✅ **18/18** справочников NSI (100%)
- ✅ **15/15** методов API ЕГР (100%)
- ✅ **11/11** полей модели Company (100%)
- ✅ **7/7** REST API endpoints (100%)
- ✅ Полная история событий компаний
- ✅ Автоматическое обновление справочников

## Быстрый старт

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Настройка переменных окружения

Скопируйте `.env.example` в `.env` и настройте:

```bash
cp .env.example .env
```

### 3. Запуск миграций

```bash
alembic upgrade head
```

### 4. Запуск сервиса

```bash
uvicorn app.main:app --reload
```

API будет доступен по адресу: http://localhost:8002

Документация: http://localhost:8002/docs

## Docker

### Запуск через Docker Compose

```bash
# Запустить все сервисы
docker-compose up -d

# Посмотреть логи
docker-compose logs -f egr-api

# Остановить
docker-compose down
```

Это запустит:
- **API сервер** (порт 8002)
  - ✅ Автоматически ждет готовности БД
  - ✅ Автоматически применяет миграции (`alembic upgrade head`)
  - ✅ Создает все 18 справочных таблиц
  - ✅ Создает таблицу событий компаний
- **Celery Worker** - обработка фоновых задач
- **Celery Beat** - планировщик периодических задач

### Проверка работы миграций

После запуска Docker можно проверить, что миграции применились:

```bash
# Проверить логи API
docker-compose logs egr-api | grep -i migration

# Подключиться к БД и проверить таблицы
docker-compose exec db psql -U postgres -d tendex_db -c "\dt egr_*"
docker-compose exec db psql -U postgres -d tendex_db -c "\dt ref_*"
```

### Пересоздание с чистой БД

```bash
# Остановить и удалить контейнеры
docker-compose down

# Удалить volumes (ОСТОРОЖНО: удалит все данные!)
docker-compose down -v

# Запустить заново (миграции применятся автоматически)
docker-compose up -d
```

## API Endpoints

### Компании (Companies)

#### Получить профиль компании

```
GET /api/v1/companies/{unp}
```

Параметры:
- `unp` - УНП компании (9 цифр)
- `force_refresh` - принудительное обновление (по умолчанию: false)

#### Поиск компаний по названию

```
GET /api/v1/companies/search?name={название}&limit=50
```

Параметры:
- `name` - название компании (минимум 3 символа)
- `limit` - максимальное количество результатов (по умолчанию: 50, макс: 100)

#### Получить события компании

```
GET /api/v1/companies/{unp}/events
```

Возвращает список событий компании (регистрация, ликвидация, банкротство и т.д.)

#### Фильтрация по статусу

```
GET /api/v1/companies/by-state/{state_id}?limit=100
```

Параметры:
- `state_id` - ID состояния (1-13)
  - 1: Действующий
  - 2: Исключен из ЕГР
  - 3: Находится в процессе ликвидации
  - 4: Процедура банкротства
  - 5-13: другие состояния

#### Получить сырые данные

```
GET /api/v1/companies/{unp}/raw?api_type=auto
```

#### Сравнить API

```
GET /api/v1/companies/{unp}/compare
```

### Справочники (References)

#### Список доступных справочников

```
GET /api/v1/references/
```

#### Получить данные справочника

```
GET /api/v1/references/{ref_type}?limit=1000&offset=0
```

Доступные типы справочников:
- `statuses` - Статусы компаний
- `creation-methods` - Способы создания
- `entity-types` - Виды объектов (ЮЛ/ИП)
- `authorities` - Органы ЕГР
- `liquidation-methods` - Способы ликвидации
- `ved` - Виды экономической деятельности
- `countries` - Страны мира
- `soato` - СОАТО (территории РБ)
- `foundations` - Основания для внесения
- `events` - События субъектов
- `street-types` - Типы улиц
- `room-types` - Типы помещений
- `room-categories` - Виды помещений
- `settlement-types` - Типы населенных пунктов
- `document-types` - Виды документов
- `currencies` - Валюты
- `positions` - Должности
- `opf` - ОПФ

#### Получить элемент справочника

```
GET /api/v1/references/{ref_type}/{id}
```

#### Поиск в справочнике

```
GET /api/v1/references/{ref_type}/search?q={запрос}&limit=100
```

## Celery Tasks

### Синхронизация конкретной компании

```python
from app.tasks.sync_tasks import sync_specific_company

sync_specific_company.delay(191688516)
```

### Синхронизация событий компании

```python
from app.tasks.sync_tasks import sync_company_events

sync_company_events.delay(191688516)
```

### Переобработка ошибочных записей

```python
from app.tasks.sync_tasks import reprocess_failed_rows

reprocess_failed_rows.delay()
```

### Обновление справочников

```python
# Базовое обновление (5 справочников)
from app.tasks.sync_tasks import update_reference_tables
update_reference_tables.delay()

# Расширенное обновление (все 18 справочников)
from app.tasks.sync_tasks import update_all_references_advanced
update_all_references_advanced.delay()
```

### Автоматические задачи (Celery Beat)

- **Ежедневная синхронизация**: 3:00 UTC+3
- **Обновление справочников**: 4:00 UTC+3 (ежедневно)
- **Расширенное обновление справочников**: каждое воскресенье в 2:00
- **Переобработка ошибок**: каждую субботу в 5:00

## Архитектура

```
workers/egr_aggregator/
├── app/
│   ├── api/v1/endpoints/     # REST API endpoints
│   ├── core/                 # Core configuration
│   ├── crud/                 # CRUD operations
│   ├── database/             # SQLAlchemy models
│   ├── schemas/              # Pydantic schemas
│   ├── services/             # Business logic
│   └── tasks/                # Celery tasks
├── migrations/               # Alembic migrations
├── tests/                    # Tests
└── docker/                   # Docker configuration
```

## База данных

### Основные таблицы

#### Таблицы компаний
- `egr_companies` - основная таблица компаний (с 11 полями)
- `egr_company_names_history` - история названий
- `egr_company_addresses_history` - история адресов
- `egr_company_ved_history` - история кодов ВЭД
- `egr_company_contacts_history` - контактная информация
- `egr_company_events` - события компаний (регистрация, ликвидация, банкротство)
- `egr_raw_company_data` - буфер сырых данных из API
- `egr_sync_history` - история синхронизаций

#### Справочные таблицы (18 шт.)
- `ref_statuses` - Статусы компаний (TSI00219)
- `ref_creation_methods` - Способы создания (TSI00208)
- `ref_entity_types` - Виды объектов (TSI00211)
- `ref_authorities` - Органы ЕГР (TSI00212)
- `ref_liquidation_methods` - Способы ликвидации (TSI00228)
- `ref_ved` - Виды экономической деятельности (TSI00114)
- `ref_countries` - Страны мира (TSI00201)
- `ref_soato` - СОАТО - территории РБ (TSI00202)
- `ref_foundations` - Основания для внесения (TSI00213)
- `ref_events` - События субъектов (TSI00223)
- `ref_street_types` - Типы улиц (TSI00226)
- `ref_room_types` - Типы помещений (TSI00227)
- `ref_room_categories` - Виды помещений (TSI00234)
- `ref_settlement_types` - Типы населенных пунктов (TSI00239)
- `ref_document_types` - Виды документов (TSI00206)
- `ref_currencies` - Валюты (TSI00204)
- `ref_positions` - Должности (TSI00207)
- `ref_opf` - ОПФ (TSI00203)

## Реализованные методы API ЕГР

Сервис поддерживает **все 15 методов** из официальной документации API ЕГР:

### Базовая информация
- ✅ `getBaseInfoByRegNum/{regNum}` - получение общих данных о субъекте
- ✅ `getBaseInfoByPeriod/{startDate}/{endDate}` - общие данные за период

### Адреса
- ✅ `getAddressByRegNum/{regNum}` - текущий адрес
- ✅ `getAllAddressByRegNum/{regNum}` - адреса с историей
- ✅ `getAddressByPeriod/{startDate}/{endDate}` - адреса за период

### Названия
- ✅ `getJurNamesByRegNum/{regNum}` - текущее название ЮЛ
- ✅ `getAllJurNamesByRegNum/{regNum}` - названия ЮЛ с историей
- ✅ `getJurNamesByPeriod/{startDate}/{endDate}` - названия за период

### ВЭД
- ✅ `getVEDByRegNum/{regNum}` - текущий ВЭД
- ✅ `getAllVEDByRegNum/{regNum}` - ВЭД с историей
- ✅ `getVEDByPeriod/{startDate}/{endDate}` - ВЭД за период

### ФИО индивидуальных предпринимателей
- ✅ `getIPFIOByRegNum/{regNum}` - текущее ФИО ИП
- ✅ `getAllIPFIOByRegNum/{regNum}` - ФИО с историей
- ✅ `getIPFIOByPeriod/{startDate}/{endDate}` - ФИО за период

### События
- ✅ `getEventByRegNum/{regNum}` - события компании
- ✅ `getEventByPeriod/{startDate}/{endDate}` - события за период

### Поиск
- ✅ `getShortInfoByRegName/{name}` - поиск по названию
- ✅ `getShortInfoByRegNum/{regNum}` - краткая информация
- ✅ `getShortInfoByPeriod/{startDate}/{endDate}` - краткая информация за период
- ✅ `getRegNumByState/{state}` - список УНП по статусу

## Интеграция с Tendex

Сервис использует общую базу данных Tendex (`tendex_db`).

Все таблицы имеют префикс `egr_` для избежания конфликтов.

## Мониторинг

### Health Check

```
GET /api/v1/health
```

### Readiness Check

```
GET /api/v1/health/ready
```

## Разработка

### Создание новой миграции

```bash
alembic revision -m "description"
```

### Применение миграций

```bash
alembic upgrade head
```

### Откат миграции

```bash
alembic downgrade -1
```
## Лицензия

MIT







