-- Скрипт для проверки состояния индексов
SELECT 
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) as size,
    idx_scan as scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes 
JOIN pg_indexes USING (indexname)
WHERE schemaname = 'public'
ORDER BY tablename, indexname;