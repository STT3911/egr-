-- =====================================================
-- Наполнение справочников из egr_raw_company_data
-- =====================================================
-- Этот скрипт извлекает данные из JSON в таблице 
-- egr_raw_company_data и заполняет справочники
-- 
-- Запускать после каждой загрузки новых данных
-- =====================================================

-- ---------------------------------------------------------
-- 1. Наполнение статусов (ref_statuses)
-- Источник: data->>'base_info'->>'nsi00219'
-- ---------------------------------------------------------
INSERT INTO ref_statuses (id, name, system_id)
SELECT DISTINCT
    ((data::jsonb->'base_info'->'nsi00219'->>'nksost')::int) as id,
    (data::jsonb->'base_info'->'nsi00219'->>'vnsostk') as name,
    ((data::jsonb->'base_info'->'nsi00219'->>'nsi00219')::int) as system_id
FROM egr_raw_company_data
WHERE 
    data::jsonb->'base_info'->'nsi00219' IS NOT NULL
    AND data::jsonb->'base_info'->'nsi00219'->>'nksost' IS NOT NULL
ON CONFLICT (id) DO UPDATE 
SET 
    name = EXCLUDED.name,
    updated_at = NOW();

-- Статистика
DO $$
DECLARE
    row_count INTEGER;
BEGIN
    GET DIAGNOSTICS row_count = ROW_COUNT;
    RAISE NOTICE '✅ ref_statuses: обработано % записей', row_count;
END $$;

-- ---------------------------------------------------------
-- 2. Наполнение способов создания (ref_creation_methods)
-- Источник: data->>'base_info'->>'nsi00208'
-- ---------------------------------------------------------
INSERT INTO ref_creation_methods (id, name, system_id)
SELECT DISTINCT
    ((data::jsonb->'base_info'->'nsi00208'->>'nkscrt')::int) as id,
    (data::jsonb->'base_info'->'nsi00208'->>'vnscrtp') as name,
    ((data::jsonb->'base_info'->'nsi00208'->>'nsi00208')::int) as system_id
FROM egr_raw_company_data
WHERE 
    data::jsonb->'base_info'->'nsi00208' IS NOT NULL
    AND data::jsonb->'base_info'->'nsi00208'->>'nkscrt' IS NOT NULL
ON CONFLICT (id) DO UPDATE 
SET 
    name = EXCLUDED.name,
    updated_at = NOW();

DO $$
DECLARE
    row_count INTEGER;
BEGIN
    GET DIAGNOSTICS row_count = ROW_COUNT;
    RAISE NOTICE '✅ ref_creation_methods: обработано % записей', row_count;
END $$;

-- ---------------------------------------------------------
-- 3. Наполнение типов объектов (ref_entity_types)
-- Источник: data->>'base_info'->>'nsi00211'
-- Важно: в документации nvob, но в JSON nkvob
-- ---------------------------------------------------------
INSERT INTO ref_entity_types (id, name, system_id)
SELECT DISTINCT
    ((data::jsonb->'base_info'->'nsi00211'->>'nkvob')::int) as id,
    (data::jsonb->'base_info'->'nsi00211'->>'vnvobp') as name,
    ((data::jsonb->'base_info'->'nsi00211'->>'nsi00211')::int) as system_id
FROM egr_raw_company_data
WHERE 
    data::jsonb->'base_info'->'nsi00211' IS NOT NULL
    AND data::jsonb->'base_info'->'nsi00211'->>'nkvob' IS NOT NULL
ON CONFLICT (id) DO UPDATE 
SET 
    name = EXCLUDED.name,
    updated_at = NOW();

DO $$
DECLARE
    row_count INTEGER;
BEGIN
    GET DIAGNOSTICS row_count = ROW_COUNT;
    RAISE NOTICE '✅ ref_entity_types: обработано % записей', row_count;
END $$;

-- ---------------------------------------------------------
-- 4. Наполнение способов ликвидации (ref_liquidation_methods)
-- Источник: data->>'base_info'->>'nsi00228'
-- ---------------------------------------------------------
INSERT INTO ref_liquidation_methods (id, name, system_id)
SELECT DISTINCT
    ((data::jsonb->'base_info'->'nsi00228'->>'nkslkv')::int) as id,
    (data::jsonb->'base_info'->'nsi00228'->>'vnslkvp') as name,
    ((data::jsonb->'base_info'->'nsi00228'->>'nsi00228')::int) as system_id
FROM egr_raw_company_data
WHERE 
    data::jsonb->'base_info'->'nsi00228' IS NOT NULL
    AND data::jsonb->'base_info'->'nsi00228'->>'nkslkv' IS NOT NULL
ON CONFLICT (id) DO UPDATE 
SET 
    name = EXCLUDED.name,
    updated_at = NOW();

DO $$
DECLARE
    row_count INTEGER;
BEGIN
    GET DIAGNOSTICS row_count = ROW_COUNT;
    RAISE NOTICE '✅ ref_liquidation_methods: обработано % записей', row_count;
END $$;

-- ---------------------------------------------------------
-- 5. Наполнение органов (ref_authorities) - СЛОЖНЫЙ
-- Органы могут быть в трех местах:
-- А. Текущий орган учета (nsi00212)
-- Б. Орган создания (nsi00212CRT)
-- В. Орган ликвидации (nsi00212LKV)
-- ---------------------------------------------------------
INSERT INTO ref_authorities (id, name, system_id)
SELECT id, 
       MAX(name) as name,  -- Берем MAX(name) для группировки дубликатов
       MAX(system_id) as system_id
FROM (
    -- А. Текущий орган учета (nsi00212)
    SELECT 
        ((data::jsonb->'base_info'->'nsi00212'->>'nkuz')::int) as id,
        (data::jsonb->'base_info'->'nsi00212'->>'vnuzp') as name,
        ((data::jsonb->'base_info'->'nsi00212'->>'nsi00212')::int) as system_id
    FROM egr_raw_company_data 
    WHERE 
        data::jsonb->'base_info'->'nsi00212' IS NOT NULL
        AND data::jsonb->'base_info'->'nsi00212'->>'nkuz' IS NOT NULL
        AND data::jsonb->'base_info'->'nsi00212'->>'vnuzp' IS NOT NULL
    
    UNION ALL
    
    -- Б. Орган создания (nsi00212CRT)
    SELECT 
        ((data::jsonb->'base_info'->'nsi00212CRT'->>'nkuz')::int) as id,
        (data::jsonb->'base_info'->'nsi00212CRT'->>'vnuzp') as name,
        ((data::jsonb->'base_info'->'nsi00212CRT'->>'nsi00212')::int) as system_id
    FROM egr_raw_company_data 
    WHERE 
        data::jsonb->'base_info'->'nsi00212CRT' IS NOT NULL
        AND data::jsonb->'base_info'->'nsi00212CRT'->>'nkuz' IS NOT NULL
        AND data::jsonb->'base_info'->'nsi00212CRT'->>'vnuzp' IS NOT NULL
    
    UNION ALL
    
    -- В. Орган ликвидации (nsi00212LKV)
    SELECT 
        ((data::jsonb->'base_info'->'nsi00212LKV'->>'nkuz')::int) as id,
        (data::jsonb->'base_info'->'nsi00212LKV'->>'vnuzp') as name,
        ((data::jsonb->'base_info'->'nsi00212LKV'->>'nsi00212')::int) as system_id
    FROM egr_raw_company_data 
    WHERE 
        data::jsonb->'base_info'->'nsi00212LKV' IS NOT NULL
        AND data::jsonb->'base_info'->'nsi00212LKV'->>'nkuz' IS NOT NULL
        AND data::jsonb->'base_info'->'nsi00212LKV'->>'vnuzp' IS NOT NULL
) as all_auths
WHERE id IS NOT NULL AND name IS NOT NULL
GROUP BY id
ON CONFLICT (id) DO UPDATE 
SET 
    name = EXCLUDED.name,
    updated_at = NOW();

DO $$
DECLARE
    row_count INTEGER;
BEGIN
    GET DIAGNOSTICS row_count = ROW_COUNT;
    RAISE NOTICE '✅ ref_authorities: обработано % записей', row_count;
END $$;

-- ---------------------------------------------------------
-- Итоговая статистика
-- ---------------------------------------------------------
DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '═══════════════════════════════════════════════════';
    RAISE NOTICE '📊 ИТОГОВАЯ СТАТИСТИКА СПРАВОЧНИКОВ';
    RAISE NOTICE '═══════════════════════════════════════════════════';
    RAISE NOTICE 'Статусы: % записей', (SELECT COUNT(*) FROM ref_statuses);
    RAISE NOTICE 'Способы создания: % записей', (SELECT COUNT(*) FROM ref_creation_methods);
    RAISE NOTICE 'Типы объектов: % записей', (SELECT COUNT(*) FROM ref_entity_types);
    RAISE NOTICE 'Органы: % записей', (SELECT COUNT(*) FROM ref_authorities);
    RAISE NOTICE 'Способы ликвидации: % записей', (SELECT COUNT(*) FROM ref_liquidation_methods);
    RAISE NOTICE '═══════════════════════════════════════════════════';
END $$;





