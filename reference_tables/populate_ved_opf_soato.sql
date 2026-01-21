-- =====================================================
-- Наполнение справочников ВЭД, ОПФ, СОАТО
-- =====================================================
-- Извлекает данные из уже обработанных таблиц истории
-- =====================================================

-- ---------------------------------------------------------
-- 1. Наполнение справочника ВЭД (ref_ved)
-- Источник: egr_company_ved_history
-- ---------------------------------------------------------

-- Создаем unique constraint на code, если его нет
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ref_ved_code_unique'
    ) THEN
        ALTER TABLE ref_ved ADD CONSTRAINT ref_ved_code_unique UNIQUE (code);
        RAISE NOTICE '✅ Created UNIQUE constraint on ref_ved.code';
    END IF;
END $$;

-- Вставляем уникальные записи
INSERT INTO ref_ved (code, name)
SELECT DISTINCT
    ved_code as code,
    COALESCE(MAX(ved_name), 'Без названия') as name  -- Берем MAX name для группировки
FROM egr_company_ved_history
WHERE 
    ved_code IS NOT NULL 
    AND ved_code != ''
    AND ved_code != '00000'  -- Исключаем "Сведения отсутствуют"
GROUP BY ved_code
ON CONFLICT (code) DO UPDATE 
SET 
    name = COALESCE(EXCLUDED.name, ref_ved.name),
    updated_at = NOW();

-- Статистика
DO $$
DECLARE
    row_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO row_count FROM ref_ved;
    RAISE NOTICE '✅ ref_ved: % записей', row_count;
END $$;

-- ---------------------------------------------------------
-- 2. Наполнение справочника СОАТО (ref_soato)
-- Источник: egr_company_addresses_history
-- ---------------------------------------------------------
-- Примечание: В текущей схеме нет отдельных полей для СОАТО,
-- но можно добавить их позже, если они появятся в данных
DO $$
BEGIN
    RAISE NOTICE '⚠️  ref_soato: Требуется дополнительный анализ структуры адресов';
END $$;

-- ---------------------------------------------------------
-- 3. Наполнение справочника ОПФ (ref_opf)
-- Источник: Справочник должен загружаться из API или JSON
-- ---------------------------------------------------------
-- Примечание: ОПФ не хранится в истории, нужно извлечь из raw_data
-- Или загрузить из внешнего источника
DO $$
BEGIN
    RAISE NOTICE '⚠️  ref_opf: Требуется загрузка из внешнего источника';
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
    RAISE NOTICE 'ВЭД (ref_ved): % записей', (SELECT COUNT(*) FROM ref_ved);
    RAISE NOTICE 'СОАТО (ref_soato): % записей', (SELECT COUNT(*) FROM ref_soato);
    RAISE NOTICE 'ОПФ (ref_opf): % записей', (SELECT COUNT(*) FROM ref_opf);
    RAISE NOTICE '═══════════════════════════════════════════════════';
END $$;
