# Парсинг не запускается — что проверить

## 1. Celery worker и beat должны быть запущены

Парсинг по расписанию (каждые 30 сек) и через API в фоне идут через **Celery**. Должны работать оба контейнера:

```bash
docker compose ps
# Должны быть в состоянии Up: egr_celery_worker, egr_celery_beat
```

Если их нет:

```bash
docker compose up -d egr-celery-worker egr-celery-beat
```

Проверить логи воркера:

```bash
docker compose logs -f egr-celery-worker
# Должны появляться задачи process_pending_raw каждые ~30 сек, если есть необработанные записи
```

---

## 2. Запуск парсинга вручную (без API и Celery)

Самый надёжный способ — вызвать обогащение и парсинг **внутри контейнера API** (без очереди):

```bash
docker compose exec egr-api python /app/scripts/run-enrich-and-parse.py --limit 50000 --rounds 10
```

Так парсинг не зависит от Celery и API-ключа.

---

## 3. Запуск через API (run-parsing.sh)

Скрипт `./scripts/run-parsing.sh` дергает API. Если в .env задан **ALLOWED_API_KEYS**, запросу нужен заголовок **X-API-Key**:

```bash
# В .env задан ALLOWED_API_KEYS=your-secret-key
API_KEY=your-secret-key ./scripts/run-parsing.sh 5000 true
```

Или в development без ключей: в .env указать `APP_ENV=development` и не задавать `ALLOWED_API_KEYS`.

---

## 4. Нет данных для парсинга

Парсинг обрабатывает только записи, у которых уже есть **names, addresses, ved** (обогащённые). Если в сырых данных только base_info — сначала нужно обогащение:

```bash
docker compose exec egr-api python /app/scripts/run-enrich-and-parse.py --limit 50000 --rounds 5
```

Проверить, сколько записей ждут обработки:

```bash
docker compose exec egr_db psql -U postgres -d egr_db -c "
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE processed_at IS NULL) AS pending,
  COUNT(*) FILTER (WHERE NOT (data ? 'names')) AS needs_enrich
FROM egr_raw_company_data;
"
```

- **pending** — ещё не распаршены (могут ждать обогащения).
- **needs_enrich** — без names/addresses/ved, им нужен шаг обогащения через API.

---

## Кратко

| Цель | Команда |
|-----|--------|
| Запустить worker + beat | `docker compose up -d egr-celery-worker egr-celery-beat` |
| Парсинг вручную в контейнере | `docker compose exec egr-api python /app/scripts/run-enrich-and-parse.py --limit 50000 --rounds 10` |
| Парсинг через API с ключом | `API_KEY=ваш_ключ ./scripts/run-parsing.sh 5000` |
| Проверить очередь | `docker compose logs -f egr-celery-worker` |
