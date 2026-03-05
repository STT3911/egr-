GIAS Workers
============

Назначение
----------
- Загрузка планов закупок с gias.by в PostgreSQL.
- Инкрементальная синхронизация (мониторинг обновлений) и полная (за выбранные годы).
- Исправление названий компаний (company_name по УНП).
- Подготовка очереди изменений для будущей индексации в Elasticsearch (сам воркер ES не входит).

Зависимости
-----------
- Python 3.11+
- PostgreSQL 13+ (тестировалось на 15)
- Pip-пакеты: requests, psycopg2-binary, python-dotenv, schedule
- (Опционально) Docker с compose-сервисами `gias_sync` / `gias_full_sync` / `gias_fix_companies`.

Установка (локально)
--------------------
```bash
pip install -r requirements.txt
```

Переменные окружения
--------------------
База данных (обязательно):
- DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

Полная синхронизация:
- GIAS_SYNC_YEARS="2026"            # годы через запятую; по умолчанию 2026
- GIAS_FULL_SYNC_LOOP=true|false    # режим цикла, по умолчанию true
- GIAS_FULL_SYNC_INTERVAL=3600      # секунды между циклами, по умолчанию час

Резерв (пока не используется в коде): GIAS_SYNC_MODE, GIAS_SYNC_INTERVAL, GIAS_MAX_PAGES, GIAS_REQUEST_DELAY.

Ключевые скрипты
----------------
- `gias_plans.py` — инкрементальная синхронизация:
  - Читает/пишет `max_date.ts` (timestamp в мс) для фильтрации по dtUpdate.
  - Годы: текущий-1, текущий, текущий+1.
  - Берёт страницы поиска (`search_plans`), затем детали плана (`get_plan_details`), сохраняет в БД.
  - Бесконечный цикл с паузой 10 секунд между итерациями.
- `gias_plans_all.py` — полная синхронизация:
  - Годы из `GIAS_SYNC_YEARS` или дефолт [2026].
  - Получает `totalPages` через `get_pagination_info`, проходит все страницы.
  - `skip_list.txt` для пропуска уже обработанных UUID.
  - Режим цикла с интервалом (по умолчанию 3600 сек); CLI: `--loop/--no-loop`, `--interval`.
- `fix_plans.py` — исправление компаний:
  - Ищет `company_name IS NULL` в `gias_plans_companies` батчами по 25.
  - По последнему плану УНП тянет детали, обновляет `gias_plans_companies` и `gias_plans.name_of_company`.
- `sync_scheduler.py` — оставлен только ночной триггер full-sync; инкрементальный сервис запускать отдельно (он бесконечный).

Поток данных (на план)
----------------------
1) `search_plans` (POST /search/api/v1/search/plans, page/pageSize/year/sort=dtUpdate DESC).
2) Для каждого UUID: `get_plan_details` (GET /plan/api/v1/plans/{uuid}).
3) `Database.save_plan`:
   - Если версия > 1 — ставит старым версиям по `chain_uuid` `state='OLD'`.
   - Upsert плана по `uuid`.
   - Ставит события `delete` для старых позиций цепочки, удаляет их, вставляет новые позиции и событие `create`.
   - Upsert справочников ОКРБ (при пустом name подставляет code).
   - Нормализация поиска: `ё->е`, lower, `-` -> `_`, убрать `:!?'"«»;,.`, схлопнуть пробелы.
4) Коммит; лог синка — в `gias_sync_log`.

Таблицы (создаются кодом)
-------------------------
- gias_plans (pk uuid, chain_uuid, version, state, даты, id_number, unp, name_of_company, year, approve/post info)
- gias_plans_companies (pk unp, company_name)
- gias_okrb_0081995 (pk code, name not null)
- gias_okrb_0072012 (pk code, name not null)
- gias_plans_items (pk uuid, plan_chain_uuid, public_number, goods_name, okrb codes, type, суммы, fin_year, procedure_month, search_text)
- gias_plans_items теперь также хранит единицы измерения: unit_code, unit_name
- gias_plans_items_changes (id, gias_plans_items_id, event=create/delete, processed ts nullable)
- gias_sync_log (статистика синков)
Индексы: chain_uuid/dt_update/year на plans; chain_uuid на items; partial index processed IS NULL на changes.

Состояние и логи
----------------
- `max_date.ts` — последний dtUpdate (мс) для инкрементального.
- `skip_list.txt` — обработанные UUID для полного.
- Логи: монтировать `./logs/gias` в `/app/logs` (Docker).
- Чтобы сохранять `max_date.ts`/`skip_list.txt` между рестартами — смонтируйте `/app` или используйте volume `gias_data`.

Docker
------
- Образ из `Dockerfile` (CMD по умолчанию `python gias_plans.py`).
- Compose-сервисы:
  - `gias_sync` — инкрементальный (long-running).
  - `gias_full_sync` — полный; по умолчанию цикл раз в час; годы из `GIAS_SYNC_YEARS`.
  - `gias_fix_companies` — одноразовый фикс.
- После правок env пересоберите/перезапустите контейнеры.

Индексация в ES
---------------
Пока нет. Очередь `gias_plans_items_changes` наполняется событиями create/delete; нужен отдельный воркер, который читает необработанные записи, индексирует/удаляет в ES и проставляет `processed`.

Особенности
-----------
- Дубликаты: PK + upsert по планам; позиции удаляются перед вставкой новых.
- Версионирование: старые версии по chain_uuid получают state='OLD'.
- ОКРБ: name = code, если пришёл пустой, чтобы не нарушать NOT NULL.



