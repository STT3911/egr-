# Договоры GIAS

## Что загружается

Реестр договоров читается через публичные запросы GIAS:

- `POST https://gias.by/search/api/v1/search/contracts` — список договоров;
- `GET https://gias.by/contract/api/v1/contract/{contractId}` — полная карточка.

Запрос страницы:

```json
{
  "baseContractId": null,
  "page": 0,
  "pageSize": 100,
  "sortField": "dtUpdate",
  "sortOrder": "DESC"
}
```

Сортировка по `dtUpdate` нужна для быстрого инкрементального обновления.

## Схема обработки

1. Индексатор постранично сохраняет краткие карточки в `gias_contracts`.
2. Номер следующей страницы хранится в `gias_contract_sync_state`. После сбоя
   или перезапуска первичный обход продолжается с последней завершённой
   страницы.
3. Очередь деталей выбирает договоры со статусом `pending` или `error` и
   получает полную карточку.
4. Позиции договора нормализуются в `gias_contract_positions`.
5. Исходные ответы без потерь сохраняются в `raw_summary` и `raw_detail`.
   Поэтому документы, подписи, платежи, счета, закупки и остальные вложенные
   блоки доступны даже тогда, когда для них нет отдельной колонки.
6. Заказчик и поставщик связываются с `egr_companies` отдельными внешними
   ключами.

Ошибки деталей повторяются с экспоненциальной задержкой. Успешные страницы
индекса и отдельные карточки фиксируются независимо, поэтому повторный запуск
идемпотентен.

## Разрешение компаний

Для каждого УНП заказчика и поставщика действует следующий порядок:

1. использовать существующую запись `egr_companies`;
2. проверить уже загруженные данные GRP;
3. запросить EGR и GRP через общий механизм проверки УНП;
4. если оба реестра однозначно сообщили, что запись не найдена, создать
   минимальную карточку из данных GIAS (`source = gias`);
5. записать `customer_company_id` или `provider_company_id` в договор.

Если EGR позднее вернёт полную карточку, источник и поля минимальной записи
обновляются, а UUID компании не меняется — связи договоров сохраняются.
Временная ошибка внешнего реестра не считается отсутствием компании и не
приводит к преждевременному созданию заглушки.

## Задачи и нагрузка

Договоры обслуживает существующий worker тяжёлых задач
`egr-celery-worker-heavy` с очередью `heavy` и concurrency 1:

- индекс — каждые 2 минуты, не более 50 страниц за запуск;
- полные карточки — каждую минуту, по 100 договоров, новый запрос каждые
  `0,33` секунды, не более четырёх запросов одновременно;
- компании и связи — каждые 5 минут, по 20 уникальных УНП.

Первичный индекс содержит сотни тысяч договоров и заполняется постепенно.
Ограниченные пакеты не удерживают память пропорционально размеру реестра,
между пакетами worker может выполнять другие тяжёлые задачи, а обычная очередь
Celery не блокируется.

Основные настройки:

```dotenv
GIAS_CONTRACT_SYNC_ENABLED=true
GIAS_CONTRACT_PAGE_SIZE=100
GIAS_CONTRACT_INDEX_BATCH_PAGES=50
GIAS_CONTRACT_DETAIL_BATCH_SIZE=100
GIAS_CONTRACT_REQUEST_INTERVAL_SECONDS=0.33
GIAS_CONTRACT_DETAIL_CONCURRENCY=4
GIAS_CONTRACT_COMPANY_BATCH_SIZE=20
GIAS_CONTRACT_REQUEST_DELAY_SECONDS=0.2
GIAS_CONTRACT_INCREMENTAL_LOOKBACK_HOURS=2
```

## Развёртывание

```bash
docker compose build egr-api egr-celery-worker-heavy
docker compose run --rm egr-api alembic upgrade head
docker compose up -d egr-api egr-celery-beat egr-celery-worker-heavy
```

Проверка прогресса:

```sql
SELECT * FROM gias_contract_sync_state;

SELECT detail_status, count(*)
FROM gias_contracts
GROUP BY detail_status;

SELECT
  count(*) FILTER (WHERE customer_company_id IS NULL AND customer_unp IS NOT NULL)
    AS customers_unlinked,
  count(*) FILTER (WHERE provider_company_id IS NULL AND provider_unp IS NOT NULL)
    AS providers_unlinked
FROM gias_contracts;
```

## API

- `GET /api/v1/gias/contracts` — компактный список; фильтры `unp`, `role`,
  `state`, `q`, пагинация `offset`/`limit`;
- `GET /api/v1/gias/contracts/{contractId}` — нормализованные позиции и полный
  исходный `raw_detail`;
- `POST /api/v1/gias/contracts/sync` — ручной запуск индекса;
- `POST /api/v1/gias/contracts/fetch-details` — ручной пакет деталей;
- `POST /api/v1/gias/contracts/resolve-companies` — ручное связывание компаний.

Три `POST`-операции требуют `X-API-Key`.
