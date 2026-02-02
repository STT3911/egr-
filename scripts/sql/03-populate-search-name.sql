-- Функция для нормализации названия компании.
-- Сначала приводим к нижнему регистру, затем удаляем ОПФ и спецсимволы (иначе заглавные удалялись бы шаблоном [^а-яёa-z]).
CREATE OR REPLACE FUNCTION normalize_company_name(name_text TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN TRIM(REGEXP_REPLACE(
        REGEXP_REPLACE(
            REGEXP_REPLACE(
                LOWER(COALESCE(name_text, '')),
                '\y(ооо|одо|зао|оао|пао|чуп|чпту|ип|уп|рнуп|гпу|флип|пк|кфх|сзоо|сзоао|доо|общество\s+с\s+ограниченной\s+ответственностью|общество\s+с\s+дополнительной\s+ответственностью|закрытое\s+акционерное\s+общество|открытое\s+акционерное\s+общество|частное\s+предприятие|частное\s+унитарное\s+предприятие|частное\s+торговое\s+унитарное\s+предприятие|частное\s+производственно\s*[\s\-]?\s*торговое\s+предприятие|республиканское\s+унитарное\s+предприятие|государственное\s+учреждение\s+образования|религиозная\s+община|обособленное\s+подразделение|филиал|представительство)\y',
                ' ',
                'gi'
            ),
            '[^а-яёa-z0-9\s]',
            ' ',
            'g'
        ),
        '\s+',
        ' ',
        'g'
    ));
END;
$$ LANGUAGE plpgsql;

-- Заполняем поле search_name для существующих записей (если оно пустое)
DO $$
DECLARE
    total_records INTEGER;
    updated_count INTEGER := 0;
    batch_size INTEGER := 5000;
    batch_result INTEGER;
    start_time TIMESTAMP;
    end_time TIMESTAMP;
BEGIN
    -- Проверяем, есть ли колонка search_name
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'egr_company_names_history' 
        AND column_name = 'search_name'
    ) THEN
        start_time := clock_timestamp();
        
        -- Считаем записи без search_name
        EXECUTE 'SELECT COUNT(*) FROM egr_company_names_history WHERE search_name IS NULL OR search_name = ''''' INTO total_records;
        
        RAISE NOTICE 'Найдено записей для обновления: %', total_records;
        
        IF total_records > 0 THEN
            -- Обновляем записи партиями
            WHILE updated_count < total_records LOOP
                EXECUTE '
                    WITH batch AS (
                        SELECT id
                        FROM egr_company_names_history
                        WHERE search_name IS NULL OR search_name = ''''
                        ORDER BY id
                        LIMIT $1
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE egr_company_names_history nh
                    SET search_name = normalize_company_name(
                        COALESCE(nh.full_name_ru, nh.short_name_ru, nh.full_name_by, '''')
                    )
                    FROM batch b
                    WHERE nh.id = b.id'
                USING batch_size;
                GET DIAGNOSTICS batch_result = ROW_COUNT;
                
                IF batch_result IS NULL OR batch_result = 0 THEN
                    EXIT;
                END IF;
                
                updated_count := updated_count + batch_result;
                RAISE NOTICE 'Обновлено % записей (всего: % из %)', batch_result, updated_count, total_records;
                
                -- Пауза между батчами
                PERFORM pg_sleep(0.05);
            END LOOP;
            
            end_time := clock_timestamp();
            RAISE NOTICE 'Заполнение search_name завершено за % секунд. Обновлено записей: %', 
                EXTRACT(EPOCH FROM (end_time - start_time)), updated_count;
        ELSE
            RAISE NOTICE 'Поле search_name уже заполнено для всех записей';
        END IF;
    ELSE
        RAISE NOTICE 'Колонка search_name не существует в таблице egr_company_names_history';
    END IF;
END $$;

-- Чистим пустые значения после заполнения
UPDATE egr_company_names_history 
SET search_name = NULL 
WHERE search_name = '';