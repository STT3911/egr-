# Подробное описание заполнения таблиц планов закупок GIAS

## Обзор

Система планов закупок GIAS состоит из трех основных таблиц БД и одного индекса Elasticsearch:
- `gias_plans` - основная информация о планах закупок
- `gias_plans_items` - позиции (закупки) в планах
- `gias_plans_companies` - справочник компаний-заказчиков
- `gias_plans_items_idx` - индекс Elasticsearch для полнотекстового поиска по позициям планов

---

## 1. Таблица `gias_plans`

### Назначение
Основная таблица, содержащая информацию о планах закупок организаций.

### Скрипты заполнения
- **`gias_plans.py`** - инкрементальная загрузка (режим мониторинга)
- **`gias_plans_all.py`** - полная загрузка всех планов

### Процесс заполнения

#### Шаг 1: Получение списка планов
Скрипты обращаются к API поиска планов:
```python
POST https://gias.by/search/api/v1/search/plans
```
Параметры запроса:
- `page` - номер страницы (пагинация)
- `pageSize` - размер страницы (40-50 записей)
- `sortField` - поле сортировки (`dtUpdate`)
- `sortOrder` - порядок сортировки (`DESC`)
- `year` - год планов (2024, 2025 и т.д.)

#### Шаг 2: Получение детальной информации о плане
Для каждого плана из списка выполняется запрос:
```python
GET https://gias.by/plan/api/v1/plans/{uuid}
```

#### Шаг 3: Обработка версий планов
Если план имеет версию больше 1, все предыдущие версии с тем же `chain_uuid` помечаются как `OLD`:
```52:52:gias_plans.py
if plan['version'] > 1:
    cur.execute("UPDATE gias_plans SET state = 'OLD' WHERE chain_uuid=%s", (plan['chainUuid'], ))
```

#### Шаг 4: Вставка/обновление записи
Используется `INSERT ... ON DUPLICATE KEY UPDATE` для вставки новой записи или обновления существующей:

```98:123:gias_plans.py
cur.execute("INSERT INTO `gias_plans` (`uuid`, `dt_create`, `dt_update`, `state`, `post_date`, `version`, `id_number`, `unp`, `name_of_company`, `year`, `approve_person`, `post_person`, `approve_date`, `chain_uuid`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE uuid = %s, dt_update = %s, state = %s, post_date = %s, version = %s, id_number = %s, approve_person=%s, post_person=%s, approve_date = %s, name_of_company = %s", (
    plan['uuid'],
    dt_create,
    dt_update,
    plan['state'],
    post_date,
    plan['version'],
    plan['identificationNumber'],
    plan['unp'],
    plan['nameOfCompany'],
    plan['year'],
    plan_details['approvePerson'],
    plan_details['postPerson'],
    approve_date,
    plan['chainUuid'],
    plan['uuid'],
    dt_update,
    plan['state'],
    post_date,
    plan['version'],
    plan['identificationNumber'],
    plan_details['approvePerson'],
    plan_details['postPerson'],
    approve_date,
    plan['nameOfCompany']
))
```

### Поля таблицы и источники данных

| Поле | Источник | Описание |
|------|----------|----------|
| `uuid` | `plan['uuid']` | Уникальный идентификатор версии плана |
| `dt_create` | `plan['dtCreate']` | Дата создания (конвертируется из timestamp) |
| `dt_update` | `plan['dtUpdate']` | Дата обновления (конвертируется из timestamp) |
| `state` | `plan['state']` | Статус плана (ACTIVE, OLD и т.д.) |
| `post_date` | `plan['postDate']` | Дата публикации (конвертируется из timestamp) |
| `version` | `plan['version']` | Версия плана |
| `id_number` | `plan['identificationNumber']` | Идентификационный номер плана |
| `unp` | `plan['unp']` | УНП организации-заказчика |
| `name_of_company` | `plan['nameOfCompany']` | Название организации-заказчика |
| `year` | `plan['year']` | Год плана |
| `approve_person` | `plan_details['approvePerson']` | Лицо, утвердившее план |
| `post_person` | `plan_details['postPerson']` | Лицо, опубликовавшее план |
| `approve_date` | `plan_details['approveDate']` | Дата утверждения (конвертируется из timestamp) |
| `chain_uuid` | `plan['chainUuid']` | Уникальный идентификатор цепочки версий плана |

### Особенности инкрементальной загрузки (`gias_plans.py`)
- Использует файл `max_date.ts` для отслеживания последней обработанной даты
- Обрабатывает только планы с `dtUpdate` больше сохраненного значения
- Работает в бесконечном цикле с паузой 10 секунд между итерациями
- Останавливается при достижении планов с датой обновления меньше `max_updated`

### Особенности полной загрузки (`gias_plans_all.py`)
- Обрабатывает все планы указанного года
- Использует список `skip_list` для пропуска уже обработанных планов
- Обрабатывает несколько лет последовательно (например, 2024 и 2025)
- Использует логирование для отслеживания прогресса

---

## 2. Таблица `gias_plans_items`

### Назначение
Содержит детальную информацию о каждой позиции (закупке) в планах закупок.

### Скрипты заполнения
- **`gias_plans.py`** - через функцию `procPurchase()`
- **`gias_plans_all.py`** - через функцию `procPurchase()`

### Процесс заполнения

#### Шаг 1: Удаление старых позиций
Перед добавлением новых позиций все существующие позиции плана удаляются:
```93:93:gias_plans.py
cur.execute("DELETE FROM gias_plans_items WHERE plan_chain_uuid =%s", (plan['chainUuid'], ))
```

#### Шаг 2: Обработка каждой позиции
Для каждой позиции из массива `plan_details['purchases']` вызывается функция `procPurchase()`:

```29:72:gias_plans.py
def procPurchase(purchase, plan_chain_uuid):
    cur.execute("INSERT IGNORE INTO gias_okrb_0081995 (code, name) VALUES (%s, %s)", (purchase['okrb0081995Code'], purchase['okrb0081995Name']))
    cur.execute("INSERT IGNORE INTO gias_okrb_0072012 (code, name) VALUES (%s, %s)", (purchase['okrb0072012Code'], purchase['okrb0072012Name']))

    approx_value = 0
    budget_cost = 0
    fund_cost = 0
    inner_cost = 0
    fin_year = 0

    for appr_cost in purchase['approximateCosts']:
        budget_cost = budget_cost + appr_cost['budgetCost']
        fund_cost = fund_cost + appr_cost['fundCost']
        inner_cost = inner_cost + appr_cost['innerCost']
        fin_year = appr_cost['finYear'] 

    month_str_arr = []
    for pm in purchase['procedureMonths']:
        month_str_arr.append(str(pm))

    search_text = normalizeSearchText(purchase['goodsName'])

    try:
        cur.execute("INSERT INTO `gias_plans_items` (`uuid`, `plan_chain_uuid`, `public_number`, `goods_name`, `okrb_0072012_code`, `okrb_0081995_code`, `type`, `approx_value`, `budget_cost`, `fund_cost`, `inner_cost`, `fin_year`, `procedure_month`, `search_text`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", (
            purchase['id'],
            plan_chain_uuid,
            purchase['publicNumber'],
            purchase['goodsName'],
            purchase['okrb0072012Code'],
            purchase['okrb0081995Code'],
            purchase['type'],
            purchase['approximateValue'],
            budget_cost,
            fund_cost,
            inner_cost,
            fin_year,
            ",".join(month_str_arr),
            search_text
        ))
        mydb.commit()
    except Exception as e:
        print(e)
        print(cur.statement)
    return search_text
```

### Детальный процесс обработки позиции

1. **Заполнение справочников ОКРБ**:
   - `gias_okrb_0081995` - классификатор ОКРБ 0081995
   - `gias_okrb_0072012` - классификатор ОКРБ 0072012
   - Используется `INSERT IGNORE` для избежания дубликатов

2. **Агрегация финансовых данных**:
   - Проходится по массиву `approximateCosts`
   - Суммируются значения:
     - `budget_cost` - бюджетные средства
     - `fund_cost` - средства фондов
     - `inner_cost` - внутренние средства
   - Берется `finYear` из последнего элемента массива

3. **Обработка месяцев процедур**:
   - Массив `procedureMonths` преобразуется в строку через запятую
   - Например: `[1, 2, 3]` → `"1,2,3"`

4. **Нормализация текста для поиска**:
   - Функция `normalizeSearchText()` обрабатывает название товара/услуги:
     - Замена "ё" на "е"
     - Приведение к нижнему регистру
     - Обработка слов с дефисами (разбиение на отдельные слова)
     - Удаление специальных символов: `:!?-'()"«»;,.`
     - Замена дефисов на подчеркивания

5. **Вставка записи**:
   - Используется обычный `INSERT` (не `INSERT IGNORE`)
   - После каждой вставки выполняется `commit()`

### Поля таблицы и источники данных

| Поле | Источник | Описание |
|------|----------|----------|
| `uuid` | `purchase['id']` | Уникальный идентификатор позиции |
| `plan_chain_uuid` | `plan_chain_uuid` (параметр) | Связь с планом через chain_uuid |
| `public_number` | `purchase['publicNumber']` | Публичный номер позиции |
| `goods_name` | `purchase['goodsName']` | Название товара/услуги |
| `okrb_0072012_code` | `purchase['okrb0072012Code']` | Код ОКРБ 0072012 |
| `okrb_0081995_code` | `purchase['okrb0081995Code']` | Код ОКРБ 0081995 |
| `type` | `purchase['type']` | Тип закупки |
| `approx_value` | `purchase['approximateValue']` | Примерная стоимость |
| `budget_cost` | Сумма `approximateCosts[].budgetCost` | Бюджетные средства |
| `fund_cost` | Сумма `approximateCosts[].fundCost` | Средства фондов |
| `inner_cost` | Сумма `approximateCosts[].innerCost` | Внутренние средства |
| `fin_year` | `approximateCosts[].finYear` | Финансовый год |
| `procedure_month` | `purchase['procedureMonths']` | Месяцы процедур (строка через запятую) |
| `search_text` | `normalizeSearchText(purchase['goodsName'])` | Нормализованный текст для поиска |

### Важные особенности
- При обновлении плана все старые позиции удаляются и создаются заново
- Каждая позиция обрабатывается отдельно с индивидуальным commit
- При ошибке вставки выводится сообщение об ошибке и SQL-запрос, но обработка продолжается

---

## 3. Таблица `gias_plans_companies`

### Назначение
Справочник компаний-заказчиков, участвующих в планах закупок. Содержит информацию об организациях по их УНП.

### Скрипты заполнения
- **`fixes/fix_plans.py`** - заполнение/обновление названий компаний

### Процесс заполнения

#### Механизм работы
Таблица заполняется не напрямую из основных скриптов загрузки планов, а через отдельный скрипт исправления данных.

#### Скрипт `fixes/fix_plans.py`

```15:29:fixes/fix_plans.py
def fix_company(unp):
    cur.execute("SELECT * FROM gias_plans WHERE unp = %s ORDER BY dt_update DESC LIMIT 1", (unp, ))
    row = cur.fetchone()
    resp = prox.get("https://gias.by/plan/api/v1/plans/"+row['uuid'])
    try:
        resp_data = resp.json()
    except:
        print(resp, row['uuid'])
        time.sleep(5)
        return
    company_name = resp_data['nameOfCompany']
    print(company_name, unp)
    cur.execute("UPDATE gias_plans_companies SET company_name = %s WHERE unp = %s", (company_name, unp))
    cur.execute("UPDATE gias_plans SET name_of_company = %s WHERE unp = %s", (company_name, unp))
    mydb.commit()
```

#### Алгоритм работы скрипта

1. **Поиск записей с пустым названием**:
   ```python
   SELECT * FROM gias_plans_companies WHERE company_name IS NULL LIMIT 25
   ```

2. **Для каждой найденной записи**:
   - Находится последний план с данным УНП в таблице `gias_plans`
   - Загружается детальная информация о плане через API
   - Извлекается актуальное название компании
   - Обновляется запись в `gias_plans_companies`
   - Обновляется название компании во всех планах с данным УНП

3. **Цикл обработки**:
   - Скрипт работает в цикле до тех пор, пока есть записи с `company_name IS NULL`
   - Обрабатывает по 25 записей за раз
   - Пауза 1 секунда между итерациями

### Предполагаемая структура таблицы
Судя по коду, таблица содержит:
- `unp` - УНП организации (первичный ключ или уникальный индекс)
- `company_name` - название компании (может быть NULL)

### Важные особенности
- Таблица не заполняется напрямую при загрузке планов
- Заполнение происходит асинхронно через отдельный скрипт
- Скрипт может использоваться для исправления/обновления данных о компаниях
- Возможно, таблица создается через триггеры БД или отдельные SQL-скрипты при инициализации БД

---

## 4. Индекс Elasticsearch `gias_plans_items_idx`

### Назначение
Индекс для полнотекстового поиска по позициям планов закупок.

### Скрипт заполнения
- **`gias_plans_elastic.py`** - синхронизация данных с Elasticsearch

### Процесс заполнения

#### Механизм работы через очередь изменений
Индекс заполняется не напрямую при вставке в `gias_plans_items`, а через таблицу-очередь `gias_plans_items_changes`.

#### Предполагаемый механизм создания записей в очереди
Таблица `gias_plans_items_changes` вероятно заполняется через триггеры БД:
- При `INSERT` в `gias_plans_items` создается запись с `event = 'create'`
- При `DELETE` из `gias_plans_items` создается запись с `event = 'delete'`

#### Обработка очереди (`gias_plans_elastic.py`)

##### Функция `tick()` - обработка создания и обновления

```41:62:gias_plans_elastic.py
def tick():
    cursor.execute('''SELECT gias_plans.`year`, gias_plans_items.id, gias_plans_items.search_text, gias_plans_items.okrb_0072012_code, gias_plans_items_changes.id AS queue_id,  gias_plans_items_changes.event FROM gias_plans_items 
    JOIN gias_plans ON gias_plans_items.plan_chain_uuid = gias_plans.chain_uuid 
    JOIN gias_plans_items_changes ON gias_plans_items_changes.gias_plans_items_id = gias_plans_items.id
    WHERE gias_plans_items_changes.processed IS NULL
    LIMIT 500''')

    for row in cursor.fetchall():
        if row['event'] == 'create':
            search_text_es = normalizeSearchText(row['search_text'])
            rec = {
                    'id' : row['id'],
                    'search_text' : search_text_es,
                    'is_closed' : 0,
                    'okrb' : row['okrb_0072012_code'],
                    'year' : row['year']
            }
            resp = es.index(index="gias_plans_items_idx", id=row['id'], document=rec)
        elif row['event'] == 'delete':
            es.delete(index="gias_plans_items_idx", id=row['id'])
        cursor.execute("UPDATE gias_plans_items_changes SET processed = NOW() WHERE id=%s", (row['queue_id'],))
    mydb.commit()
```

##### Функция `tick_delete()` - обработка удалений

```64:74:gias_plans_elastic.py
def tick_delete():
    cursor.execute('''SELECT gias_plans_items_changes.id AS queue_id, gias_plans_items_id, event FROM gias_plans_items_changes WHERE gias_plans_items_changes.processed IS NULL and gias_plans_items_changes.event = 'delete' LIMIT 500''')

    for row in cursor.fetchall():
        if row['event'] == 'delete':
            try:
                es.delete(index="gias_plans_items_idx", id=row['gias_plans_items_id'])
            except:
                ...
        cursor.execute("UPDATE gias_plans_items_changes SET processed = NOW() WHERE id=%s", (row['queue_id'],))
    mydb.commit()
```

### Алгоритм работы

1. **Выборка необработанных изменений**:
   - Выбираются записи из `gias_plans_items_changes` с `processed IS NULL`
   - Ограничение: 500 записей за раз

2. **Обработка события 'create'**:
   - Дополнительная нормализация `search_text` через `normalizeSearchText()`
   - Создание документа в Elasticsearch:
     ```python
     {
         'id': row['id'],
         'search_text': search_text_es,
         'is_closed': 0,
         'okrb': row['okrb_0072012_code'],
         'year': row['year']
     }
     ```
   - Используется `es.index()` с указанием `id` записи

3. **Обработка события 'delete'**:
   - Удаление документа из индекса через `es.delete()`
   - Обработка ошибок (если документ уже удален)

4. **Отметка как обработанное**:
   - Устанавливается `processed = NOW()` в таблице `gias_plans_items_changes`

5. **Цикл работы**:
   - Скрипт работает в бесконечном цикле
   - Вызываются обе функции: `tick()` и `tick_delete()`
   - Пауза 5 секунд между итерациями

### Структура документа в Elasticsearch

| Поле | Источник | Описание |
|------|----------|----------|
| `id` | `gias_plans_items.id` | ID позиции плана (используется как ID документа) |
| `search_text` | `normalizeSearchText(gias_plans_items.search_text)` | Нормализованный текст для поиска |
| `is_closed` | Константа `0` | Флаг закрытости (всегда 0 для планов) |
| `okrb` | `gias_plans_items.okrb_0072012_code` | Код ОКРБ 0072012 |
| `year` | `gias_plans.year` | Год плана |

### Особенности нормализации для Elasticsearch
Функция `normalizeSearchText()` в `gias_plans_elastic.py` немного отличается от версии в `gias_plans.py`:
- Не добавляет точку с запятой и запятую в список заменяемых символов
- Результат приводится к нижнему регистру (в `gias_plans.py` это делается в начале функции)

### Важные особенности
- Синхронизация происходит асинхронно через очередь изменений
- Обработка идёт батчами по 500 записей
- При ошибках удаления (документ уже удален) ошибка игнорируется
- Используется идемпотентная операция `es.index()` - можно вызывать многократно

---

## Схема взаимодействия компонентов

```
┌─────────────────────────────────────────────────────────────┐
│                    API GIAS.BY                               │
│  /search/api/v1/search/plans  →  /plan/api/v1/plans/{uuid}   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              gias_plans.py / gias_plans_all.py              │
│  • Получение списка планов                                  │
│  • Получение детальной информации                           │
│  • Обработка версий                                         │
└──────┬──────────────────────────────┬───────────────────────┘
       │                              │
       ▼                              ▼
┌──────────────────┐        ┌──────────────────────┐
│  gias_plans      │        │  gias_plans_items    │
│  (основная       │        │  (позиции планов)    │
│   информация)    │        │                      │
└──────────────────┘        └──────┬───────────────┘
                                    │
                                    │ (триггер БД)
                                    ▼
                          ┌─────────────────────────┐
                          │ gias_plans_items_      │
                          │ changes (очередь)      │
                          └──────┬─────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────────┐
                    │  gias_plans_elastic.py    │
                    │  • Обработка очереди      │
                    │  • Синхронизация с ES     │
                    └──────┬─────────────────────┘
                           │
                           ▼
                    ┌──────────────────────┐
                    │  Elasticsearch       │
                    │  gias_plans_items_idx│
                    └──────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              gias_plans (по УНП)                            │
│                    │                                         │
│                    ▼                                         │
│         fixes/fix_plans.py                                   │
│         • Поиск пустых названий                              │
│         • Загрузка через API                                │
│         • Обновление данных                                  │
│                    │                                         │
│                    ▼                                         │
│         gias_plans_companies                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Резюме

### Таблица `gias_plans`
- **Заполнение**: Прямое из API через `gias_plans.py` / `gias_plans_all.py`
- **Частота**: Инкрементально (каждые 10 сек) или полная загрузка
- **Обновление**: `ON DUPLICATE KEY UPDATE` по ключу
- **Особенность**: Версионирование через `chain_uuid` и `state = 'OLD'`

### Таблица `gias_plans_items`
- **Заполнение**: Прямое из API через функцию `procPurchase()`
- **Частота**: При каждом обновлении плана
- **Обновление**: Полное удаление и пересоздание при обновлении плана
- **Особенность**: Агрегация финансовых данных, нормализация текста

### Таблица `gias_plans_companies`
- **Заполнение**: Асинхронно через `fixes/fix_plans.py`
- **Частота**: По требованию для исправления данных
- **Обновление**: `UPDATE` по УНП
- **Особенность**: Не заполняется напрямую при загрузке планов

### Индекс `gias_plans_items_idx`
- **Заполнение**: Асинхронно через `gias_plans_elastic.py` из очереди изменений
- **Частота**: Непрерывно (каждые 5 сек)
- **Обновление**: Через очередь `gias_plans_items_changes` (вероятно, триггеры БД)
- **Особенность**: Дополнительная нормализация текста, батч-обработка по 500 записей

