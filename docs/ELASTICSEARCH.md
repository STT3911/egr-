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

По умолчанию включен режим `ELASTICSEARCH_REQUIRE_SYNCED=true`: `/lookup`
использует Elasticsearch только после завершенного полного прохода и проверки
числа документов. Во время первой индексации, после прерванной индексации или
при слишком большой очереди изменений используется SQL-поиск.

## Запуск

```bash
docker compose up -d --build elasticsearch egr-api egr-celery-worker egr-celery-beat
```

Elasticsearch доступен на `http://localhost:9200`.

## Первичная индексация

Через API, в фоне через Celery. Для действующего сервиса не указывайте
`recreate=true`: существующий индекс продолжит обслуживать запросы, а задача
добавит отсутствующие документы.

```bash
curl -X POST "http://localhost:8002/api/v1/companies/search/reindex?recreate=false&resume=true&async_run=true" \
  -H "X-API-Key: <API_KEY>"
```

Или синхронно из контейнера:

```bash
docker compose exec -T egr-api python scripts/reindex_elasticsearch.py
```

Для тестового прогона можно ограничить объем:

```bash
docker compose exec -T egr-api python scripts/reindex_elasticsearch.py --limit 1000
```

После каждой успешной пачки сохраняется курсор. Повтор той же команды
продолжает проход с последнего УНП. Чтобы намеренно начать новый проход без
удаления индекса, добавьте `--no-resume`.

`--recreate` сначала удаляет действующий индекс. Используйте его только при
изменении mapping и в согласованное окно обслуживания; для восстановления
после заполнения диска он не нужен.

Если Elasticsearch ранее показывал `flood stage disk watermark`, сначала
освободите место и убедитесь, что блокировка снята:

```bash
docker compose exec -T egr-api curl -sS \
  'http://elasticsearch:9200/egr_companies/_settings?filter_path=*.settings.index.blocks.*'
```

Ответ `{}` означает, что индекс снова доступен для записи.

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

Поле `reindex` показывает сохраненный курсор, состояние `running`, `partial`,
`failed` или `complete`, а также числа документов и компаний после проверки.

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
