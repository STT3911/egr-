-- Скрипт для проверки состояния индексов
SELECT 
    s.schemaname,
    s.relname AS tablename,
    s.indexrelname AS indexname,
    pg_size_pretty(pg_relation_size(s.indexrelid)) AS size,
    s.idx_scan AS scans,
    s.idx_tup_read AS tuples_read,
    s.idx_tup_fetch AS tuples_fetched
FROM pg_stat_user_indexes s
WHERE s.schemaname = 'public'
ORDER BY s.relname, s.indexrelname;
