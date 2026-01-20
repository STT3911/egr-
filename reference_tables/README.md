# Справочники EGR (Reference Tables)

## Описание

Эта директория содержит скрипты для создания и наполнения справочных таблиц из данных ЕГР.

### Справочники

1. **ref_statuses** - Статусы компаний (Действующий, Ликвидирован и т.д.)
2. **ref_creation_methods** - Способы создания компаний
3. **ref_entity_types** - Типы объектов (ЮЛ/ИП)
4. **ref_authorities** - Регистрирующие органы (Исполкомы, Министерства)
5. **ref_liquidation_methods** - Способы ликвидации

---

## Структура файлов

```
reference_tables/
├── create_tables.sql           # DDL для создания таблиц справочников
├── populate_from_raw.sql       # Наполнение из egr_raw_company_data
├── load_from_json.py          # Загрузка из JSON файлов
└── README.md                  # Эта инструкция
```

---

## Использование

### Вариант 1: Из существующей таблицы egr_raw_company_data

Если данные уже загружены в таблицу `egr_raw_company_data`:

```bash
# 1. Создать таблицы справочников
docker-compose exec db psql -U postgres -d egr_db -f /app/reference_tables/create_tables.sql

# 2. Наполнить справочники
docker-compose exec db psql -U postgres -d egr_db -f /app/reference_tables/populate_from_raw.sql
```

### Вариант 2: Из JSON файлов напрямую

Если у вас есть JSON файлы с данными:

```bash
# 1. Создать таблицы справочников
docker-compose exec db psql -U postgres -d egr_db -f /app/reference_tables/create_tables.sql

# 2. Загрузить из JSON файлов
docker-compose exec egr_celery_worker python reference_tables/load_from_json.py \
    /path/to/file1.json \
    /path/to/file2.json
```

### Вариант 3: Из локальной машины

```bash
# 1. Создать таблицы
psql -h localhost -p 5433 -U postgres -d egr_db -f workers/egr_aggregator/reference_tables/create_tables.sql

# 2. Загрузить данные
cd workers/egr_aggregator
python reference_tables/load_from_json.py data/file1.json data/file2.json
```

---

## Структура таблиц

### ref_statuses

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER | Код состояния (PK) |
| name | TEXT | Наименование |
| system_id | INTEGER | ID справочника в ЕГР |
| created_at | TIMESTAMP | Дата создания |
| updated_at | TIMESTAMP | Дата обновления |

**Пример данных**:
```sql
SELECT * FROM ref_statuses;
-- id  | name                | system_id
-- ----+--------------------+-----------
-- 1   | Действующий        | 219
-- 2   | Ликвидирован       | 219
-- 3   | В стадии ликвидации| 219
```

### ref_creation_methods

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER | Код способа (PK) |
| name | TEXT | Наименование |
| system_id | INTEGER | ID справочника в ЕГР |

**Пример данных**:
```sql
SELECT * FROM ref_creation_methods LIMIT 3;
-- id  | name                           | system_id
-- ----+--------------------------------+-----------
-- 1   | Создано вновь                  | 208
-- 2   | Реорганизация (слияние)        | 208
-- 3   | Реорганизация (присоединение)  | 208
```

### ref_entity_types

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER | Код вида (PK) |
| name | TEXT | Наименование |
| system_id | INTEGER | ID справочника в ЕГР |

**Пример данных**:
```sql
SELECT * FROM ref_entity_types;
-- id  | name                            | system_id
-- ----+---------------------------------+-----------
-- 1   | Юридическое лицо                | 211
-- 2   | Индивидуальный предприниматель  | 211
```

### ref_authorities

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER | Код органа (PK) |
| name | TEXT | Наименование |
| system_id | INTEGER | ID справочника в ЕГР |

**Пример данных**:
```sql
SELECT * FROM ref_authorities LIMIT 5;
-- id   | name                                    | system_id
-- -----+-----------------------------------------+-----------
-- 500  | Минский городской исполнительный комитет| 212
-- 501  | Гомельский облисполком                  | 212
-- 502  | Брестский облисполком                   | 212
```

### ref_liquidation_methods

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER | Код способа (PK) |
| name | TEXT | Наименование |
| system_id | INTEGER | ID справочника в ЕГР |

**Пример данных**:
```sql
SELECT * FROM ref_liquidation_methods LIMIT 3;
-- id  | name                    | system_id
-- ----+-------------------------+-----------
-- 1   | Ликвидация добровольная | 228
-- 2   | Ликвидация по решению суда | 228
-- 3   | Банкротство            | 228
```

---

## Проверка данных

### Количество записей

```sql
-- Все справочники
SELECT 
    'ref_statuses' as table_name, COUNT(*) as count FROM ref_statuses
UNION ALL
SELECT 
    'ref_creation_methods', COUNT(*) FROM ref_creation_methods
UNION ALL
SELECT 
    'ref_entity_types', COUNT(*) FROM ref_entity_types
UNION ALL
SELECT 
    'ref_authorities', COUNT(*) FROM ref_authorities
UNION ALL
SELECT 
    'ref_liquidation_methods', COUNT(*) FROM ref_liquidation_methods;
```

### Примеры запросов

```sql
-- Найти все статусы
SELECT * FROM ref_statuses ORDER BY id;

-- Найти все исполкомы
SELECT * FROM ref_authorities WHERE name LIKE '%исполком%';

-- Статистика по типам объектов
SELECT 
    et.name,
    COUNT(c.id) as companies_count
FROM ref_entity_types et
LEFT JOIN egr_companies c ON c.entity_type_id = et.id
GROUP BY et.id, et.name;
```

---

## Обновление справочников

Справочники можно обновлять в любое время:

```bash
# Из таблицы egr_raw_company_data
docker-compose exec db psql -U postgres -d egr_db \
    -f /app/reference_tables/populate_from_raw.sql

# Из новых JSON файлов
docker-compose exec egr_celery_worker python reference_tables/load_from_json.py \
    new_data1.json new_data2.json
```

**Важно**: Скрипты используют `ON CONFLICT DO UPDATE`, поэтому:
- Существующие записи обновятся (если название изменилось)
- Новые записи добавятся
- Дубликаты не создадутся

---

## Интеграция с основными таблицами

После создания справочников можно добавить Foreign Keys к таблице `egr_companies`:

```sql
-- Добавить колонки для связи со справочниками
ALTER TABLE egr_companies 
    ADD COLUMN IF NOT EXISTS status_id INTEGER REFERENCES ref_statuses(id),
    ADD COLUMN IF NOT EXISTS creation_method_id INTEGER REFERENCES ref_creation_methods(id),
    ADD COLUMN IF NOT EXISTS entity_type_id INTEGER REFERENCES ref_entity_types(id),
    ADD COLUMN IF NOT EXISTS authority_id INTEGER REFERENCES ref_authorities(id),
    ADD COLUMN IF NOT EXISTS liquidation_method_id INTEGER REFERENCES ref_liquidation_methods(id);

-- Создать индексы
CREATE INDEX IF NOT EXISTS idx_egr_companies_status_id ON egr_companies(status_id);
CREATE INDEX IF NOT EXISTS idx_egr_companies_entity_type_id ON egr_companies(entity_type_id);
CREATE INDEX IF NOT EXISTS idx_egr_companies_authority_id ON egr_companies(authority_id);
```

---

## Источник данных

Данные извлекаются из JSON структур ЕГР:

| Справочник | JSON путь | Поля |
|------------|-----------|------|
| ref_statuses | `base_info.nsi00219` | nksost, vnsostk |
| ref_creation_methods | `base_info.nsi00208` | nkscrt, vnscrtp |
| ref_entity_types | `base_info.nsi00211` | nkvob, vnvobp |
| ref_authorities | `base_info.nsi00212*` | nkuz, vnuzp |
| ref_liquidation_methods | `base_info.nsi00228` | nkslkv, vnslkvp |

**Примечание**: Органы (`ref_authorities`) собираются из трех источников:
- `nsi00212` - текущий орган учета
- `nsi00212CRT` - орган создания
- `nsi00212LKV` - орган ликвидации

---

## Устранение проблем

### Ошибка: "relation does not exist"

Создайте таблицы:
```bash
docker-compose exec db psql -U postgres -d egr_db \
    -f /app/reference_tables/create_tables.sql
```

### Ошибка: "column data does not exist"

Проверьте что таблица `egr_raw_company_data` существует и содержит данные:
```sql
SELECT COUNT(*) FROM egr_raw_company_data;
```

### Пустые справочники

Если после выполнения скриптов справочники пустые:
1. Проверьте структуру JSON в `egr_raw_company_data`
2. Убедитесь что JSON содержит поля `base_info.nsi00*`
3. Попробуйте загрузить напрямую из JSON файлов

---

## Автоматизация

Для автоматического обновления справочников после загрузки новых данных:

### Вариант 1: Добавить в Celery задачу

```python
@celery_app.task
def update_reference_tables():
    """Обновить справочники после загрузки данных"""
    import subprocess
    
    result = subprocess.run([
        'psql', '-U', 'postgres', '-d', 'egr_db',
        '-f', '/app/reference_tables/populate_from_raw.sql'
    ], capture_output=True, text=True)
    
    logger.info(result.stdout)
    
    return "Reference tables updated"
```

### Вариант 2: Добавить в startup_check.py

```python
def update_references():
    """Обновить справочники"""
    script_path = '/app/reference_tables/populate_from_raw.sql'
    if os.path.exists(script_path):
        subprocess.run(['psql', '-U', 'postgres', '-d', 'egr_db', '-f', script_path])
```

---

## Полезные запросы

```sql
-- Топ-10 органов по количеству компаний
SELECT 
    ra.name,
    COUNT(c.id) as companies_count
FROM ref_authorities ra
LEFT JOIN egr_companies c ON c.authority_id = ra.id
GROUP BY ra.id, ra.name
ORDER BY companies_count DESC
LIMIT 10;

-- Распределение по статусам
SELECT 
    rs.name,
    COUNT(c.id) as count,
    ROUND(COUNT(c.id) * 100.0 / SUM(COUNT(c.id)) OVER (), 2) as percentage
FROM ref_statuses rs
LEFT JOIN egr_companies c ON c.status_id = rs.id
GROUP BY rs.id, rs.name
ORDER BY count DESC;

-- Компании ликвидированные конкретным способом
SELECT 
    c.unp,
    c.registration_date,
    c.liquidation_date,
    rlm.name as liquidation_method
FROM egr_companies c
JOIN ref_liquidation_methods rlm ON c.liquidation_method_id = rlm.id
WHERE c.liquidation_date IS NOT NULL
ORDER BY c.liquidation_date DESC
LIMIT 20;
```





