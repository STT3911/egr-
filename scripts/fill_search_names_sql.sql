-- Заполнение столбца search_name для существующих записей
-- Используем PostgreSQL функции для нормализации

-- Функция нормализации названия
CREATE OR REPLACE FUNCTION normalize_company_name(name TEXT)
RETURNS TEXT AS $$
DECLARE
    result TEXT;
BEGIN
    IF name IS NULL THEN
        RETURN NULL;
    END IF;
    
    result := LOWER(TRIM(name));
    
    -- Удаляем ОПФ (полные названия)
    result := REGEXP_REPLACE(result, '\mобщество\s+с\s+ограниченной\s+ответственностью\M', ' ', 'gi');
    result := REGEXP_REPLACE(result, '\mобщество\s+с\s+дополнительной\s+ответственностью\M', ' ', 'gi');
    result := REGEXP_REPLACE(result, '\mзакрытое\s+акционерное\s+общество\M', ' ', 'gi');
    result := REGEXP_REPLACE(result, '\mоткрытое\s+акционерное\s+общество\M', ' ', 'gi');
    result := REGEXP_REPLACE(result, '\mакционерное\s+общество\M', ' ', 'gi');
    result := REGEXP_REPLACE(result, '\mиндивидуальный\s+предприниматель\M', ' ', 'gi');
    result := REGEXP_REPLACE(result, '\mчастное\s+унитарное\s+предприятие\M', ' ', 'gi');
    result := REGEXP_REPLACE(result, '\mкоммунальное\s+унитарное\s+предприятие\M', ' ', 'gi');
    
    -- Удаляем ОПФ (сокращения)
    result := REGEXP_REPLACE(result, '\mооо\M', ' ', 'gi');
    result := REGEXP_REPLACE(result, '\mодо\M', ' ', 'gi');
    result := REGEXP_REPLACE(result, '\mзао\M', ' ', 'gi');
    result := REGEXP_REPLACE(result, '\mоао\M', ' ', 'gi');
    result := REGEXP_REPLACE(result, '\mао\M', ' ', 'gi');
    result := REGEXP_REPLACE(result, '\mип\M', ' ', 'gi');
    result := REGEXP_REPLACE(result, '\mчуп\M', ' ', 'gi');
    result := REGEXP_REPLACE(result, '\mкуп\M', ' ', 'gi');
    result := REGEXP_REPLACE(result, '\mруп\M', ' ', 'gi');
    result := REGEXP_REPLACE(result, '\mптуп\M', ' ', 'gi');
    result := REGEXP_REPLACE(result, '\mчптуп\M', ' ', 'gi');
    
    -- Удаляем все спецсимволы (оставляем только буквы, цифры, пробелы)
    result := REGEXP_REPLACE(result, '[^а-яёa-z0-9\s]', ' ', 'g');
    
    -- Заменяем множественные пробелы на один
    result := REGEXP_REPLACE(result, '\s+', ' ', 'g');
    
    result := TRIM(result);
    
    RETURN NULLIF(result, '');
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Заполняем search_name для всех существующих записей (батчами для безопасности)
UPDATE egr_company_names_history
SET search_name = normalize_company_name(COALESCE(full_name_ru, short_name_ru, full_name_by))
WHERE search_name IS NULL;

-- Создаем индекс для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_search_name_pattern 
ON egr_company_names_history(search_name varchar_pattern_ops);

-- Статистика
SELECT 
    COUNT(*) as total_records,
    COUNT(search_name) as records_with_search_name,
    COUNT(*) - COUNT(search_name) as records_without_search_name
FROM egr_company_names_history;
