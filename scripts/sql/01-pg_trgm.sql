-- Установка расширения pg_trgm для триграммного поиска
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Проверяем, что расширение установлено
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'
    ) THEN
        RAISE NOTICE 'Расширение pg_trgm установлено успешно';
    END IF;
END $$;