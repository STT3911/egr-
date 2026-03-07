-- Создание необходимых индексов для быстрого поиска
-- Основные индексы для таблицы компаний
CREATE INDEX IF NOT EXISTS idx_companies_unp ON egr_companies(unp);
CREATE INDEX IF NOT EXISTS idx_companies_created_at ON egr_companies(created_at);

-- Индексы для истории названий компаний
CREATE INDEX IF NOT EXISTS idx_names_company_id_valid 
ON egr_company_names_history(company_id, valid_to DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_names_valid_to 
ON egr_company_names_history(valid_to) 
WHERE valid_to IS NOT NULL;

-- Индексы для нормализованного поиска
CREATE INDEX IF NOT EXISTS idx_names_search_name ON egr_company_names_history(search_name);

-- Триграммные индексы для нечеткого поиска (требуют pg_trgm)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') THEN
        -- Только если расширение установлено
        CREATE INDEX IF NOT EXISTS idx_names_search_name_trgm 
        ON egr_company_names_history USING gin(search_name gin_trgm_ops);

        CREATE INDEX IF NOT EXISTS idx_names_full_name_ru_trgm 
        ON egr_company_names_history USING gin(LOWER(full_name_ru) gin_trgm_ops);

        CREATE INDEX IF NOT EXISTS idx_names_short_name_ru_trgm 
        ON egr_company_names_history USING gin(LOWER(short_name_ru) gin_trgm_ops);

        CREATE INDEX IF NOT EXISTS idx_names_full_name_by_trgm 
        ON egr_company_names_history USING gin(LOWER(full_name_by) gin_trgm_ops);
        
        RAISE NOTICE 'Триграммные индексы созданы';
    ELSE
        RAISE NOTICE 'Расширение pg_trgm не установлено, триграммные индексы не созданы';
    END IF;
END $$;

-- Индексы для поиска без учета регистра (работают всегда)
CREATE INDEX IF NOT EXISTS idx_names_full_name_ru_lower 
ON egr_company_names_history(LOWER(full_name_ru));

CREATE INDEX IF NOT EXISTS idx_names_short_name_ru_lower 
ON egr_company_names_history(LOWER(short_name_ru));

CREATE INDEX IF NOT EXISTS idx_names_full_name_by_lower 
ON egr_company_names_history(LOWER(full_name_by));

-- Очередь парсинга: быстрый выбор необработанных по updated_at (ускоряет process_pending_raw / egr_process_raw)
CREATE INDEX IF NOT EXISTS idx_egr_raw_company_data_pending
ON egr_raw_company_data (updated_at ASC)
WHERE processed_at IS NULL;

-- Проверяем созданные индексы
DO $$
DECLARE
    idx_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO idx_count 
    FROM pg_indexes 
    WHERE schemaname = 'public' 
    AND tablename IN ('egr_companies', 'egr_company_names_history');
    
    RAISE NOTICE 'Создано/проверено индексов: %', idx_count;
END $$;