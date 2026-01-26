# Исправление парсинга данных из JSON файлов

## Проблема

JSON файлы в `data/egr_json_full/` содержат только **базовую информацию** (base_info) о компаниях:
- УНП (`ngrn`)
- Дата регистрации (`dfrom`)
- Статус (`nsi00219`)
- Тип объекта (`nsi00211`)
- Органы регистрации (`nsi00212`)

**НЕ содержат:**
- ❌ Названия компаний
- ❌ Адреса
- ❌ Коды ВЭД
- ❌ Историю изменений

### Старое поведение (неправильное)
Система пыталась сразу обработать эти неполные данные в структурные таблицы, что приводило к:
- Компании без названий в БД
- Отсутствие адресов
- Отсутствие ВЭД кодов
- Ошибки при парсинге

## Решение

Реализован **3-этапный процесс загрузки**:

### Этап 1: Загрузка base_info
```python
from app.tasks.sync_tasks import load_companies_from_json
loaded = load_companies_from_json()
```

- Загружает только `base_info` в `egr_raw_company_data`
- НЕ обрабатывает в структурные таблицы
- Помечает записи как требующие обогащения

### Этап 2: Обогащение через API
```python
from app.tasks.sync_tasks import enrich_missing_raw
enriched = enrich_missing_raw(limit=10000)
```

- Для каждой записи вызывает `get_full_company_history(unp)`
- Добавляет `addresses`, `names`, `ved`
- Обновляет `egr_raw_company_data.data`

### Этап 3: Обработка в структурные таблицы
```python
from app.tasks.sync_tasks import process_pending_raw
processed = process_pending_raw(limit=10000)
```

- Парсит обогащенные данные через `CompanyMapper`
- Сохраняет в структурные таблицы:
  - `egr_companies`
  - `egr_company_names_history`
  - `egr_company_addresses_history`
  - `egr_company_ved_history`
  - `egr_company_contacts_history`

## Что исправлено

### 1. `app/tasks/sync_tasks.py` - функция `load_companies_from_json()`

**Было:**
- Загружала JSON → сразу обрабатывала в таблицы
- Создавала записи без названий

**Стало:**
- Загружает JSON → сохраняет только в `egr_raw_company_data`
- Помечает как требующие обогащения
- Выводит инструкции для следующих шагов

### 2. `app/services/mapper_service.py` - fallback логика для имен

**Было:**
```python
fallback_short = (
    base_info.get("vnaimk")  # Неправильное поле
    or base_info.get("VNAIMK")
    or base_info.get("vn")
    or base_info.get("VN")
)
```

**Стало:**
```python
fallback_short = (
    base_info.get("vn")  # Правильное поле в приоритете
    or base_info.get("vnaimk")
    or base_info.get("VNAIMK")
    or base_info.get("VN")
)
```

### 3. `auto-import-data.py` - автоматическая загрузка

**Было:**
- Запускал только `load_companies_from_json()`
- Оставлял данные неполными

**Стало:**
- Запускает все 3 этапа последовательно
- Обеспечивает полную загрузку данных
- Показывает прогресс каждого этапа

### 4. `load_json_data.py` - ручная загрузка

**Было:**
- Только загрузка из JSON

**Стало:**
- Полный 3-этапный процесс
- Опции для синхронного и асинхронного режима
- Подробная документация

### 5. Новые скрипты

**`enrich-data.py`** / **`enrich-data.sh`** / **`enrich-data.bat`**
- Удобный интерфейс для обогащения данных
- Показывает статус текущих данных
- Позволяет выбрать количество записей для обогащения

## Как использовать

### Вариант 1: Автоматическая загрузка (рекомендуется)
```bash
docker-compose up
# auto-import-data.py запустится автоматически
```

### Вариант 2: Ручная загрузка с полным процессом
```bash
python load_json_data.py --sync
```

### Вариант 3: Поэтапная загрузка
```bash
# Шаг 1: Загрузить из JSON
python -c "from app.tasks.sync_tasks import load_companies_from_json; load_companies_from_json()"

# Шаг 2: Обогатить
python enrich-data.py

# Шаг 3: Обработать (запустится автоматически через Celery)
```

## Проверка результатов

### Проверить сколько записей загружено
```sql
SELECT COUNT(*) FROM egr_raw_company_data;
```

### Проверить сколько требуют обогащения
```sql
SELECT COUNT(*) 
FROM egr_raw_company_data 
WHERE NOT (data ? 'names') 
   OR NOT (data ? 'addresses') 
   OR NOT (data ? 'ved');
```

### Проверить сколько обработано
```sql
SELECT COUNT(*) FROM egr_companies;
```

### Проверить компании с названиями
```sql
SELECT 
    c.unp,
    n.full_name_ru,
    n.short_name_ru
FROM egr_companies c
LEFT JOIN egr_company_names_history n ON n.company_id = c.id
WHERE n.valid_to IS NULL
LIMIT 10;
```

## Производительность

### Этап 1: Загрузка из JSON
- **Скорость:** ~50,000-100,000 записей/минуту
- **Время для 1.6 млн:** ~20-30 минут

### Этап 2: Обогащение через API
- **Скорость:** ~50-200 записей/минуту (зависит от API)
- **Время для 10,000:** ~50-200 минут
- **Рекомендация:** Запускать частями (по 10,000-50,000)

### Этап 3: Обработка в таблицы
- **Скорость:** ~40,000-120,000 записей/час
- **Время для 1.6 млн:** ~13-40 часов
- **Автоматизация:** Celery Beat запускает каждые 30 сек

## Важные замечания

1. **Обогащение требует времени** - для большого количества записей может потребоваться несколько часов или дней
2. **Rate limiting** - EGR API имеет ограничения, не запускайте слишком много параллельных процессов
3. **Мониторинг** - следите за логами Celery для отслеживания прогресса
4. **Ошибки** - записи с ошибками обогащения помечаются в `last_error`, их можно переобработать

## Troubleshooting

### Проблема: Данные загружены, но нет названий
**Решение:** Запустите обогащение:
```bash
python enrich-data.py
```

### Проблема: Обогащение слишком медленное
**Решение:** Обогащайте частями:
```python
from app.tasks.sync_tasks import enrich_missing_raw
for i in range(0, 100000, 10000):
    enriched = enrich_missing_raw(limit=10000)
    print(f"Enriched {enriched} records")
```

### Проблема: Ошибки при обогащении
**Решение:** Проверьте логи и переобработайте ошибки:
```sql
-- Посмотреть ошибки
SELECT unp, last_error 
FROM egr_raw_company_data 
WHERE last_error IS NOT NULL 
LIMIT 10;

-- Сбросить ошибки для повторной попытки
UPDATE egr_raw_company_data 
SET last_error = NULL 
WHERE last_error LIKE '%timeout%';
```

## Дополнительная информация

См. также:
- `data/egr_json_full/README.md` - подробности о структуре JSON файлов
- `README.md` - общая документация проекта
- `app/tasks/sync_tasks.py` - исходный код задач обработки
