# Elasticsearch

В проект добавлен Elasticsearch как быстрый индекс для поиска компаний.
Основной endpoint остается прежним:

```bash
GET /api/v1/companies/lookup?q=минск&limit=10
```

Если Elasticsearch выключен, недоступен или индекс еще пустой, API
использует старый SQL-поиск по PostgreSQL.

PostgreSQL остается источником истины. Для синхронизации используется
outbox-очередь `search_index_queue`: изменения в таблицах `egr_companies`
и `egr_company_names_history` автоматически ставят УНП в очередь через
DB-триггеры. Celery-задача `process_search_index_queue` переносит изменения
в Elasticsearch с ретраями.

По умолчанию включен режим `ELASTICSEARCH_REQUIRE_SYNCED=true`: если в
очереди есть `pending` или `failed` записи, `/lookup` временно использует
SQL-поиск, чтобы не отдавать устаревшие результаты из Elasticsearch.

## Запуск

```bash
docker compose up -d --build elasticsearch egr-api egr-celery-worker egr-celery-beat
```

Elasticsearch доступен на `http://localhost:9200`.

## Первичная индексация

Через API, в фоне через Celery:

```bash
curl -X POST "http://localhost:8002/api/v1/companies/search/reindex?recreate=true&async_run=true" \
  -H "X-API-Key: <API_KEY>"
```

Или синхронно из контейнера:

```bash
docker compose exec egr-api python scripts/reindex_elasticsearch.py --recreate
```

Для тестового прогона можно ограничить объем:

```bash
docker compose exec egr-api python scripts/reindex_elasticsearch.py --recreate --limit 1000
```

## Проверка статуса

```bash
curl "http://localhost:8002/api/v1/companies/search/status" \
  -H "X-API-Key: <API_KEY>"
```

Поле `synced=true` означает, что:

- Elasticsearch доступен;
- индекс существует;
- количество документов в индексе равно количеству компаний в БД;
- в `search_index_queue` нет `pending`/`failed` записей.

## Настройки

Основные переменные окружения:

```env
ELASTICSEARCH_ENABLED=true
ELASTICSEARCH_URL=http://elasticsearch:9200
ELASTICSEARCH_INDEX=egr_companies
ELASTICSEARCH_REQUIRE_SYNCED=true
ELASTICSEARCH_REINDEX_BATCH_SIZE=1000
ELASTICSEARCH_QUEUE_BATCH_SIZE=500
ELASTICSEARCH_QUEUE_MAX_ATTEMPTS=10
ELASTICSEARCH_QUEUE_SCHEDULE_SECONDS=30
```

При парсинге компании сервис пытается обновить документ в индексе.
Ошибка индексации логируется, но не ломает основной процесс загрузки данных.
Если ошибка случилась, УНП остается в очереди до успешной индексации или до
достижения лимита попыток.
