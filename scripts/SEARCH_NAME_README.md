# Заполнение search_name

Колонка **search_name** в таблице **egr_company_names_history** хранит нормализованное название компании для быстрого и «умного» поиска (без ОПФ, без лишних символов).

## Автоматическое заполнение

1. **При старте API**  
   Скрипт **scripts/sql/03-populate-search-name.sql** выполняется автоматически при запуске контейнера egr-api (через `scripts/init/run_sql_and_monitoring.sh`). Заполняются только строки, где `search_name` пустой.

2. **При добавлении/обновлении записей**  
   Триггер **trigger_update_search_name** (из **scripts/sql/04-create-trigger.sql**) при INSERT/UPDATE по полям названия сам заполняет `search_name`.

Итого: после первого старта и при любых новых/обновлённых названиях `search_name` заполняется без ручных действий.

## Ручной запуск (после массового импорта)

Если вы загрузили много данных мимо парсера или нужно перезаполнить поле:

```bash
# Вариант 1: через shell-скрипт (тот же SQL, что и при старте)
./scripts/fill-search-name.sh

# Вариант 2: Python (нормализация из app.utils.search_normalizer)
docker compose exec egr-api python /app/scripts/fill_search_names_python.py
```

Оба варианта обрабатывают только строки с пустым `search_name`; повторный запуск безопасен.

## Файлы

| Файл | Назначение |
|------|------------|
| **scripts/sql/03-populate-search-name.sql** | Заполнение батчами при старте и из `fill-search-name.sh` |
| **scripts/sql/04-create-trigger.sql** | Триггер авто-заполнения при INSERT/UPDATE |
| **scripts/fill-search-name.sh** | Ручной запуск заполнения (SQL) |
| **scripts/fill_search_names_python.py** | Ручной запуск через Python-нормализатор |
| **scripts/fill_search_names_sql.sql** | Альтернативный standalone SQL (ручной запуск через psql) |

## Проверка

```sql
SELECT 
  COUNT(*) AS total,
  COUNT(search_name) FILTER (WHERE search_name IS NOT NULL AND search_name != '') AS filled
FROM egr_company_names_history;
```

Или из хоста:

```bash
docker compose exec egr-api python -c "
from app.core.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
r = db.execute(text('SELECT COUNT(*) FROM egr_company_names_history WHERE search_name IS NULL OR search_name = '''')).scalar()
print(f'Rows without search_name: {r}')
db.close()
"
```
