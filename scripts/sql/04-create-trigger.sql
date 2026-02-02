-- Создание триггера для автоматического заполнения search_name

-- Сначала удаляем существующий триггер (если есть)
DROP TRIGGER IF EXISTS trigger_update_search_name ON egr_company_names_history;

-- Функция триггера: сначала LOWER, затем удаление ОПФ и спецсимволов (чтобы заглавные не удалялись).
CREATE OR REPLACE FUNCTION update_search_name()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_name = TRIM(REGEXP_REPLACE(
        REGEXP_REPLACE(
            REGEXP_REPLACE(
                LOWER(COALESCE(NEW.full_name_ru, NEW.short_name_ru, NEW.full_name_by, '')),
                '\y(ооо|зао|оао|пао|чуп|ип|уп|рнуп|гпу|флип|пк|кфх|сзоо|сзоао|доо|общество\s+с\s+ограниченной\s+ответственностью|закрытое\s+акционерное\s+общество|открытое\s+акционерное\s+общество|частное\s+унитарное\s+предприятие|республиканское\s+унитарное\s+предприятие|обособленное\s+подразделение|филиал|представительство)\y',
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
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Создаем триггер
CREATE TRIGGER trigger_update_search_name
BEFORE INSERT OR UPDATE OF full_name_ru, short_name_ru, full_name_by
ON egr_company_names_history
FOR EACH ROW
EXECUTE FUNCTION update_search_name();

-- Проверяем создание триггера
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM information_schema.triggers 
        WHERE event_object_table = 'egr_company_names_history' 
        AND trigger_name = 'trigger_update_search_name'
    ) THEN
        RAISE NOTICE 'Триггер успешно создан';
    ELSE
        RAISE NOTICE 'Не удалось создать триггер';
    END IF;
END $$;