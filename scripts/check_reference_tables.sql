-- ============================================================
-- Проверка справочников: количество записей и подозрительные значения
-- Запуск: docker exec -i egr_db psql -U postgres -d egr_db -f - < scripts/check_reference_tables.sql
-- Или: docker exec -i egr_db psql -U postgres -d egr_db < scripts/check_reference_tables.sql
-- ============================================================

\echo ''
\echo '═══════════════════════════════════════════════════════════'
\echo '  ПРОВЕРКА СПРАВОЧНИКОВ (ref_*)'
\echo '═══════════════════════════════════════════════════════════'

-- Список таблиц ref_* и количество записей
\echo ''
\echo '--- 1. Количество записей по таблицам ---'
SELECT
    schemaname,
    relname AS table_name,
    n_live_tup AS row_count
FROM pg_stat_user_tables
WHERE relname LIKE 'ref_%'
ORDER BY relname;

-- Проверка по каждой ключевой таблице: пустые/заглушки в name
\echo ''
\echo '--- 2. ref_statuses: пустые имена или заглушки "Статус N" ---'
SELECT id, name, system_id,
       CASE WHEN name IS NULL OR TRIM(name) = '' THEN 'ПУСТО'
            WHEN name ~ '^Статус [0-9]+$' THEN 'ЗАГЛУШКА'
            ELSE 'OK' END AS status
FROM ref_statuses
WHERE name IS NULL OR TRIM(name) = '' OR name ~ '^Статус [0-9]+$'
ORDER BY id;

\echo ''
\echo '--- 3. ref_creation_methods: пустые или "Способ создания N" ---'
SELECT id, name, system_id,
       CASE WHEN name IS NULL OR TRIM(name) = '' THEN 'ПУСТО'
            WHEN name ~ '^Способ создания [0-9]+$' THEN 'ЗАГЛУШКА'
            ELSE 'OK' END AS status
FROM ref_creation_methods
WHERE name IS NULL OR TRIM(name) = '' OR name ~ '^Способ создания [0-9]+$'
ORDER BY id;

\echo ''
\echo '--- 4. ref_entity_types: пустые или "Тип объекта N" ---'
SELECT id, name, system_id,
       CASE WHEN name IS NULL OR TRIM(name) = '' THEN 'ПУСТО'
            WHEN name ~ '^Тип объекта [0-9]+$' THEN 'ЗАГЛУШКА'
            ELSE 'OK' END AS status
FROM ref_entity_types
WHERE name IS NULL OR TRIM(name) = '' OR name ~ '^Тип объекта [0-9]+$'
ORDER BY id;

\echo ''
\echo '--- 5. ref_authorities: пустые или "Орган N" (первые 20 подозрительных) ---'
SELECT id, LEFT(name, 50) AS name, system_id,
       CASE WHEN name IS NULL OR TRIM(name) = '' THEN 'ПУСТО'
            WHEN name ~ '^Орган [0-9]+$' THEN 'ЗАГЛУШКА'
            ELSE 'OK' END AS status
FROM ref_authorities
WHERE name IS NULL OR TRIM(name) = '' OR name ~ '^Орган [0-9]+$'
ORDER BY id
LIMIT 20;

\echo ''
\echo '--- 6. ref_liquidation_methods: пустые или "Способ ликвидации N" ---'
SELECT id, name, system_id,
       CASE WHEN name IS NULL OR TRIM(name) = '' THEN 'ПУСТО'
            WHEN name ~ '^Способ ликвидации [0-9]+$' THEN 'ЗАГЛУШКА'
            ELSE 'OK' END AS status
FROM ref_liquidation_methods
WHERE name IS NULL OR TRIM(name) = '' OR name ~ '^Способ ликвидации [0-9]+$'
ORDER BY id;

\echo ''
\echo '--- 7. ref_ved: пустые name (первые 15) ---'
SELECT id, code, LEFT(name, 40) AS name, system_id
FROM ref_ved
WHERE name IS NULL OR TRIM(name) = ''
LIMIT 15;

\echo ''
\echo '--- 8. Сводка: таблицы с возможными заглушками ---'
WITH checks AS (
  SELECT 'ref_statuses' AS tbl, COUNT(*) AS bad FROM ref_statuses WHERE name IS NULL OR TRIM(name) = '' OR name ~ '^Статус [0-9]+$'
  UNION ALL
  SELECT 'ref_creation_methods', COUNT(*) FROM ref_creation_methods WHERE name IS NULL OR TRIM(name) = '' OR name ~ '^Способ создания [0-9]+$'
  UNION ALL
  SELECT 'ref_entity_types', COUNT(*) FROM ref_entity_types WHERE name IS NULL OR TRIM(name) = '' OR name ~ '^Тип объекта [0-9]+$'
  UNION ALL
  SELECT 'ref_authorities', COUNT(*) FROM ref_authorities WHERE name IS NULL OR TRIM(name) = '' OR name ~ '^Орган [0-9]+$'
  UNION ALL
  SELECT 'ref_liquidation_methods', COUNT(*) FROM ref_liquidation_methods WHERE name IS NULL OR TRIM(name) = '' OR name ~ '^Способ ликвидации [0-9]+$'
)
SELECT * FROM checks WHERE bad > 0;

\echo ''
\echo 'Если выше пусто — подозрительных записей нет. Если есть строки — в этих таблицах заглушки или пустые name.'
\echo '═══════════════════════════════════════════════════════════'
