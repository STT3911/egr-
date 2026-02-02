-- Диагностика: почему pending не уменьшается (0 processed).
-- С хоста (из корня проекта): docker exec -i egr_db psql -U postgres -d egr_db < scripts/sql/check-parsing-status.sql
-- Или если /app примонтирован: docker exec egr_db psql -U postgres -d egr_db -f /app/scripts/sql/check-parsing-status.sql

\echo '=== 1. Счётчики egr_raw_company_data ==='
SELECT
  COUNT(*) FILTER (WHERE processed_at IS NULL) AS pending,
  COUNT(*) FILTER (WHERE processed_at IS NOT NULL) AS processed,
  COUNT(*) FILTER (WHERE last_error IS NOT NULL AND last_error != '') AS with_error
FROM egr_raw_company_data;

\echo ''
\echo '=== 2. Примеры last_error (топ-5) ==='
SELECT LEFT(last_error, 150) AS err_sample, COUNT(*) AS cnt
FROM egr_raw_company_data
WHERE last_error IS NOT NULL AND last_error != ''
GROUP BY LEFT(last_error, 150)
ORDER BY cnt DESC
LIMIT 5;

\echo ''
\echo '=== 3. Справочники (должны быть не пусты) ==='
SELECT 'ref_creation_methods' AS tbl, COUNT(*) FROM ref_creation_methods
UNION ALL SELECT 'ref_statuses', COUNT(*) FROM ref_statuses
UNION ALL SELECT 'ref_opf', COUNT(*) FROM ref_opf
UNION ALL SELECT 'ref_authorities', COUNT(*) FROM ref_authorities;
