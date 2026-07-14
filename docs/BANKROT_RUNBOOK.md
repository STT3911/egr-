# Bankrot.gov.by: эксплуатационный runbook

## Что работает

- Celery Beat ставит ежедневную задачу `app.tasks.bankrot_tasks.sync_bankrot_cases`.
- Задача маршрутизируется в очередь `heavy`.
- Основные поля дела сохраняются в `bankrot_cases`.
- Полные JSON-разделы сохраняются в `bankrot_case_datasets`.
- Связь с компанией выполняется по `bankrot_cases.debtor_unp = egr_companies.unp`.
- Ошибка одного дочернего endpoint не останавливает остальные данные.
- Предыдущий успешный JSON не затирается при временной ошибке источника.

## Обязательные настройки

```env
BANKROT_SCHEDULE_ENABLED=true
BANKROT_SCHEDULE_SECONDS=86400
BANKROT_FETCH_RELATED_DATA=true
BANKROT_RELATED_DATASETS=
BANKROT_REFRESH_TOKEN=...
```

Пустой `BANKROT_RELATED_DATASETS` означает загрузку всех поддерживаемых наборов.
Access-токен нельзя использовать как постоянный секрет: он живёт ограниченное время.

## Деплой

```bash
cd ~/egr
git pull
docker compose run --rm egr-api alembic upgrade head
docker compose up -d --force-recreate \
  egr-api egr-celery-worker-heavy egr-celery-beat frontend grafana
```

Backend-код подключён в контейнеры как `/app`, но `--force-recreate` нужен для перечитывания
значений `.env`. Frontend пересобирается отдельно, если менялся React-код.

## Ручной запуск

```bash
docker compose exec egr-api celery -A app.tasks.celery_app call \
  app.tasks.bankrot_tasks.sync_bankrot_cases \
  --queue heavy
```

```bash
docker compose logs -f --tail=200 egr-celery-worker-heavy
```

Повторный полный запуск безопасен: используется upsert по `case_id` и
`(case_id, dataset_type)`.

## Проверка результата

В Grafana открыть дашборд **Bankrot.gov.by — полнота и качество** (`uid=bankrot-sync`).

В карточке компании:

1. Найти компанию с банкротным делом.
2. Открыть блок банкротства.
3. Нажать «Показать все сведения реестра».
4. Показать карточку, судебные решения, имущество, продажи, требования и данные управляющего.

## Типовые ошибки

### `ManagerId is not valid. Error val: 0`

Причина: использовался кабинетный `POST /messages/all`, который требует токен конкретного
управляющего. Исправленный клиент использует публичный `POST /messages` с поиском по
наименованию должника.

### `401 invalid_token`

Проверить `BANKROT_REFRESH_TOKEN`, время контейнера и доступность OIDC:

```bash
docker compose exec egr-celery-worker-heavy date -u
docker compose logs --tail=200 egr-celery-worker-heavy | grep -i '401\|refresh\|token'
```

### Много ошибок одного набора

```sql
SELECT dataset_type, count(*), left(max(fetch_error), 300)
FROM bankrot_case_datasets
WHERE fetch_error IS NOT NULL
GROUP BY dataset_type
ORDER BY count(*) DESC;
```

Можно временно ограничить наборы через `BANKROT_RELATED_DATASETS`, пересоздать heavy worker
и повторить запуск. Последние успешные payload сохранятся.

### Задача не стартует по расписанию

```bash
docker compose exec egr-celery-beat python -c \
  'from app.tasks.celery_app import celery_app; print(celery_app.conf.beat_schedule.get("bankrot-sync-cases"))'
docker compose logs --tail=200 egr-celery-beat
docker compose ps egr-celery-worker-heavy egr-celery-beat
```

## Откат

Остановить только расписание без удаления данных:

```env
BANKROT_SCHEDULE_ENABLED=false
```

```bash
docker compose up -d --force-recreate egr-celery-beat
```

Существующие карточки и API продолжат работать на последнем успешном снимке.
