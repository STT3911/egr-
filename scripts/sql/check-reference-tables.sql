-- Проверка заполнения справочников (ref_*).
-- Запуск с хоста: docker exec -i egr_db psql -U postgres -d egr_db < scripts/sql/check-reference-tables.sql

\echo '=== Количество записей по справочникам ==='
SELECT 'ref_statuses'           AS tbl, COUNT(*) AS cnt FROM ref_statuses
UNION ALL SELECT 'ref_creation_methods', COUNT(*) FROM ref_creation_methods
UNION ALL SELECT 'ref_entity_types',       COUNT(*) FROM ref_entity_types
UNION ALL SELECT 'ref_authorities',        COUNT(*) FROM ref_authorities
UNION ALL SELECT 'ref_liquidation_methods', COUNT(*) FROM ref_liquidation_methods
UNION ALL SELECT 'ref_opf',                COUNT(*) FROM ref_opf
UNION ALL SELECT 'ref_ved',                COUNT(*) FROM ref_ved
UNION ALL SELECT 'ref_countries',          COUNT(*) FROM ref_countries
UNION ALL SELECT 'ref_soato',              COUNT(*) FROM ref_soato
UNION ALL SELECT 'ref_foundations',        COUNT(*) FROM ref_foundations
UNION ALL SELECT 'ref_events',             COUNT(*) FROM ref_events
ORDER BY tbl;

\echo ''
\echo '=== Примеры записей (первые 3 по каждому основному справочнику) ==='
\echo '--- ref_creation_methods ---'
SELECT id, LEFT(name, 50) AS name FROM ref_creation_methods ORDER BY id LIMIT 3;
\echo '--- ref_authorities ---'
SELECT id, LEFT(name, 50) AS name FROM ref_authorities ORDER BY id LIMIT 3;
\echo '--- ref_entity_types ---'
SELECT id, LEFT(name, 50) AS name FROM ref_entity_types ORDER BY id LIMIT 3;
\echo '--- ref_liquidation_methods ---'
SELECT id, LEFT(name, 50) AS name FROM ref_liquidation_methods ORDER BY id LIMIT 3;
