# Выгрузка решений экономических судов

Источник: `https://service.court.gov.by/ru/juridical/judgmentresults`.
Источник требует действующую пользовательскую ASP.NET-сессию. Cookie является
секретом: не добавляйте её в Git, команды, логи или сообщения.

## Структура БД и миграция

Ревизия `court1schema` следует за `addrunit1`; добавляет только новые таблицы:

- `courts`: справочник восьми судов с идентификаторами сайта.
- `court_cases`: дела, уникальные по `(court_id, source_process_id)`.
  Номер дела — поисковое поле, а не уникальный ключ.
- `court_judgments`: решения, уникальные по `(case_id, source_document_id)`.
  Одно дело может иметь несколько решений. Сохраняются тип, дата, резолютивная
  часть, ссылка, исходные данные в JSONB и время получения.

Внешние ключи запрещают удаление суда или дела при наличии дочерних записей.
Для номера дела и даты решения добавлены индексы. Связь с компанией по УНП не
создаётся без подтверждённых данных источника. Экспортёр пока пишет в JSONL;
эта миграция сама по себе не включает импорт в PostgreSQL или фоновый сбор.

Проверки локально (с установленными зависимостями проекта и pytest):

```bash
python -m pytest -q tests/test_court_judgments.py tests/test_court_migration.py tests/test_court_export_resume.py
alembic heads
```

Тест миграции формирует SQL для PostgreSQL и отдельно проверяет ограничения и
откат в временной SQLite-базе. Это не заменяет применение на PostgreSQL dev.

После коммита в `develop` сначала обновите dev-checkout и соберите новый образ
`api`. Затем на сервере в `/home/user/egr-dev` выполните (без запуска экспорта):

```bash
docker compose --project-name egr-dev --env-file .env.dev -f deploy/dev/docker-compose.yml build api
docker compose --project-name egr-dev --env-file .env.dev -f deploy/dev/docker-compose.yml run --rm --no-deps api alembic current
docker compose --project-name egr-dev --env-file .env.dev -f deploy/dev/docker-compose.yml run --rm --no-deps api alembic upgrade head
docker compose --project-name egr-dev --env-file .env.dev -f deploy/dev/docker-compose.yml run --rm --no-deps api alembic current
docker compose --project-name egr-dev --env-file .env.dev -f deploy/dev/docker-compose.yml exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT id, name FROM courts ORDER BY id;"'
```

Ожидается ревизия `court1schema` и восемь судов. На production переносить только
после этой проверки; миграция там не запускалась. `downgrade` удаляет все три
новые таблицы вместе с накопленными судебными данными: не применять его как
безопасный способ отката приложения.

## Подготовка cookie

После входа на сайт скопируйте только значение заголовка `Cookie` в отдельный
файл вне репозитория. Допустим также заголовок `Cookie` отдельной строкой перед
значением или префикс `Cookie:`. Остальные HTTP-заголовки добавлять нельзя.
На сервере:

```bash
mkdir -p /home/user/egr-secrets
chmod 700 /home/user/egr-secrets
editor /home/user/egr-secrets/court.cookie
chmod 600 /home/user/egr-secrets/court.cookie
```

## Запуск

По умолчанию скрипт выгружает решения типа `14` за январь 2025 года для всех
восьми экономических судов. Между любыми двумя HTTP-запросами выдерживается не
менее 30 секунд (изменение от 19.10.2026), без случайной добавки по умолчанию. Дополнительную
паузу можно задать через `--delay-jitter`. Ограничение применяется также к
скачиванию документов. Быстрых автоматических повторов после ошибки нет.
Результат сохраняется построчно в JSONL:

```bash
cd /home/user/egr
python3 scripts/export_court_judgments.py \
  --cookie-file /home/user/egr-secrets/court.cookie \
  --output-dir /home/user/egr-court-exports
```

Другой период и одновременное скачивание документов:

```bash
python3 scripts/export_court_judgments.py \
  --cookie-file /home/user/egr-secrets/court.cookie \
  --date-from 01.01.2025 \
  --date-to 31.12.2025 \
  --download-documents \
  --output-dir /home/user/egr-court-exports
```

Для одного или нескольких судов повторяйте `--court`, например:

```bash
python3 scripts/export_court_judgments.py \
  --cookie-file /home/user/egr-secrets/court.cookie \
  --court 151 --court 155 \
  --output-dir /home/user/egr-court-exports
```

ID судов: `151` Брест, `152` Витебск, `153` Гомель, `154` Гродно, `155`
Минск, `156` Минская область, `157` Могилёв, `1` Верховный Суд.

Во время работы создаются `.jsonl.partial` и `.state.json`. После остановки
повторите ту же команду: уже завершённые страницы будут пропущены. После
успешного окончания partial-файл атомарно переименовывается в `.jsonl`, а
checkpoint удаляется. Если cookie истекла, скрипт завершится с кодом `2`, не
удаляя накопленный результат.

После каждого ответа клиент принимает обновления `Set-Cookie`, выданные самим
сайтом, и атомарно сохраняет актуальный набор обратно в `--cookie-file` с
правами `0600` (на Windows доступ определяется также ACL). Это позволяет
использовать продление, если сайт выдаёт новые cookies; постоянное продление
сессии этим сайтом пока не подтверждено. Полностью истёкшую или отозванную сессию, CAPTCHA,
повторный вход и блокировку аккаунта скрипт не обходит: в таком случае нужно
сначала восстановить доступ обычным способом через сайт.

Время последнего HTTP-запроса хранится рядом с cookie в скрытом файле
`.court-request-rate.txt`. Поэтому перезапуск процесса не сбрасывает
30-секундное ограничение. Не запускайте одновременно несколько экземпляров
загрузчика для одного аккаунта.

Для короткой проверки `--court 151 --max-pages 1` ограничивает обход одной
страницей и оставляет `.partial`/checkpoint для продолжения. Это не ограничение
всех HTTP-запросов: с `--download-documents` отдельно запрашивается каждый
документ, поэтому при лимите в один запрос этот флаг использовать нельзя.
