-- Проверка производительности индексов
SELECT 
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    round((idx_tup_read::numeric / NULLIF(idx_scan, 0)), 2) as avg_tuples_per_scan
FROM pg_stat_user_indexes 
WHERE schemaname = 'public'
ORDER BY idx_scan DES