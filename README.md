# ЕГР Aggregator Service

Микросервис для агрегации и обработки данных из API ЕГР Республики Беларусь.

## Возможности

- Автоматическая синхронизация данных из ЕГР
- Поддержка двух API: Mobile (быстрый) и Legacy (полный)
- Буферизация сырых данных (ELT паттерн)
- История изменений компаний (названия, адреса, ВЭД, контакты)
- История событий (регистрация, ликвидация, банкротство)
- Справочники NSI из ЕГР
- REST API для поиска компаний
- Поиск по УНП и названию с автокомплитом
- Фоновая обработка через Celery
- Docker-ready с автоматической настройкой
- Оптимизированный парсинг (до 120,000 записей/час)

## Текущее состояние базы данных

### Основные таблицы

| Таблица | Записей | Статус |
|---------|---------|--------|
| Компании | ~400,000 | Активно заполняется |
| История названий | ~235,000 | Активно |
| История адресов | ~52,000 | Активно |
| История ВЭД | ~238,000 | Активно |
| История контактов | ~37,000 | Активно |

### Справочники

| Справочник | Записей | Статус |
|------------|---------|--------|
| Статусы компаний | 6 | Загружен |
| Способы создания | 4 | Загружен |
| Типы субъектов (ЮЛ/ИП) | 2 | Загружен |
| Органы регистрации | 261 | Загружен |
| Способы ликвидации | 5 | Загружен |
| Коды ВЭД | 140+ | Загружен |

### Прогресс парсинга

- **1.6+ млн** записей сырых данных загружены
- **Автоматическая обработка**: ~40,000-120,000 записей/час
- **Парсинг работает** в фоне через Celery Beat

## Быстрый старт

### Docker Compose (рекомендуется)

```bash
# 1. Клонировать репозиторий
git clone <repository-url>
cd egr-service

# 2. Запустить все сервисы
docker-compose up -d

# 3. Проверить статус
docker-compose ps
```

Это запустит:
- **API сервер** → http://localhost:8002
- **Frontend** → http://localhost (http://localhost:5173 для dev)
- **Celery Worker** - обработка данных
- **Celery Beat** - планировщик задач
- **PostgreSQL** - база данных
- **Redis** - брокер сообщений
- **Nginx** - обратный прокси

## API Endpoints

### Документация

- **Swagger UI**: http://localhost:8002/docs
- **ReDoc**: http://localhost:8002/redoc

### Основные endpoints

#### Компании

```bash
# Получить профиль компании
GET /api/v1/companies/{unp}

# Автокомплит по УНП/названию
GET /api/v1/companies/lookup?q=500000306&limit=10

# Сырые данные компании
GET /api/v1/companies/{unp}/raw

# Статус обработки
GET /api/v1/companies/{unp}/raw/status

# Запустить парсинг вручную
POST /api/v1/companies/{unp}/parse?force=true
```

#### Справочники

```bash
# Список всех справочников
GET /api/v1/references/

# Получить данные справочника
GET /api/v1/references/statuses
GET /api/v1/references/authorities
GET /api/v1/references/ved
```

## Управление парсингом данных

### Автоматический парсинг (через Celery)

Парсинг запускается **автоматически** каждые 30 секунд:
- Обрабатывает 2000 записей за раз
- Использует 4 параллельных потока
- Скорость: ~40,000-120,000 записей/час

### Ручной запуск парсинга

**Windows:**
```cmd
.\run-parsing.bat --limit 5000
```

**Linux/Mac:**
```bash
./run-parsing.sh --limit 5000
```

Параметры:
- `--limit N` - количество записей (по умолчанию: 1000)
- `--async` - запустить в фоне через Celery

### Мониторинг прогресса

```bash
# Проверить необработанные записи
docker exec egr_db psql -U postgres -d egr_db -c "SELECT COUNT(*) FILTER (WHERE processed_at IS NULL) AS pending FROM egr_raw_company_data;"

# Проверить статистику компаний
docker exec egr_db psql -U postgres -d egr_db -c "SELECT COUNT(*) FILTER (WHERE registration_date IS NOT NULL) as with_date, COUNT(*) as total FROM egr_companies;"
```

### Управление Celery

```bash
# Перезапустить Celery
docker-compose restart egr-celery-worker

# Логи Celery
docker-compose logs -f egr-celery-worker

# Остановить автопарсинг
docker-compose stop egr-celery-beat
```

## Загрузка справочников

### Основные справочники (из raw data)

```bash
# Копировать скрипт
docker cp reference_tables/populate_from_raw.sql egr_db:/tmp/

# Выполнить
docker exec egr_db psql -U postgres -d egr_db -f /tmp/populate_from_raw.sql
```

Загружает: статусы, способы создания, типы субъектов, органы регистрации, способы ликвидации.

### Справочник ВЭД (из истории)

```bash
docker cp reference_tables/populate_ved_opf_soato.sql egr_db:/tmp/
docker exec egr_db psql -U postgres -d egr_db -f /tmp/populate_ved_opf_soato.sql
```

## База данных

### Основные таблицы

| Таблица | Описание |
|---------|----------|
| `egr_companies` | Основная таблица компаний |
| `egr_company_names_history` | История названий |
| `egr_company_addresses_history` | История адресов |
| `egr_company_ved_history` | История ВЭД |
| `egr_company_contacts_history` | Контакты |
| `egr_raw_company_data` | Буфер сырых данных |

### Справочные таблицы

- `ref_statuses` - Статусы компаний
- `ref_authorities` - Органы регистрации
- `ref_ved` - Коды ВЭД
- `ref_entity_types` - Типы субъектов
- И другие...

## Celery Tasks

### Периодические задачи

| Задача | Частота | Описание |
|--------|---------|----------|
| `process_pending_raw` | Каждые 30 сек | Парсинг данных (2000 записей) |
| `update_reference_tables` | Ежедневно 04:00 | Обновление справочников |
| `load_companies_from_json` | Ежедневно 02:00 | Загрузка из JSON |
| `reprocess_failed_rows` | Суббота 05:00 | Переобработка ошибок |

### Настройки производительности

**Текущие (оптимальные):**
- Concurrency: 4 потока
- Batch: 2000 записей
- Частота: 30 секунд
- Скорость: ~40,000-120,000/час

**Для ускорения** (docker-compose.yml):
```yaml
command: celery -A app.tasks.celery_app worker --concurrency=8
```

**Для снижения нагрузки** (app/tasks/celery_app.py):
```python
"schedule": timedelta(minutes=5),
"args": (500,),
```

## Мониторинг

### Health Check
```bash
curl http://localhost:8002/api/v1/health
```

### Логи
```bash
docker-compose logs -f egr-api        # API
docker-compose logs -f egr-celery-worker  # Celery
docker-compose logs -f egr_db         # БД
```

## Устранение неполадок

### Celery не работает
```bash
docker-compose restart egr-celery-worker
docker-compose logs -f egr-celery-worker
```

### Медленный парсинг
Увеличьте `concurrency` в docker-compose.yml:
```yaml
command: celery ... --concurrency=8
```

### Ошибки миграций
```bash
docker exec egr_db psql -U postgres -d egr_db -c "SELECT * FROM alembic_version;"
docker-compose exec egr-api alembic upgrade head
```

## Разработка

### Миграции
```bash
alembic revision --autogenerate -m "описание"
alembic upgrade head
alembic downgrade -1
```

### Тестирование
```bash
pytest
pytest --cov=app tests/
```

## Переменные окружения

```bash
# База данных
DB_HOST=db
DB_NAME=egr_db
DB_USER=postgres
DB_PASSWORD=your_password

# Redis
REDIS_URL=redis://redis:6379/3
CELERY_BROKER_URL=redis://redis:6379/4

# API
EGR_API_URL=http://egr.gov.by/api/v2/egr
EGR_MOBILE_API_URL=https://egr.gov.by/egrmobile/api/v1

# CORS
CORS_ORIGINS=http://localhost:5173,http://localhost
```

## Лицензия

MIT License

---

**Версия:** 2.0.0  
**Дата обновления:** Январь 2026  
**Статус:** Production Ready
