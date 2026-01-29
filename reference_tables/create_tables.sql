-- =====================================================
-- Справочники EGR (Reference Tables)
-- =====================================================
-- Эти таблицы содержат нормализованные справочные данные
-- из JSON структур ЕГР
-- =====================================================

-- 1. Справочник состояний (Статусы)
-- Источник: nsi00219 в JSON
CREATE TABLE IF NOT EXISTS ref_statuses (
    id INTEGER PRIMARY KEY,        -- nksost (Код состояния)
    name TEXT NOT NULL,            -- vnsostk (Наименование)
    system_id INTEGER,             -- nsi00219 (ID справочника ЕГР)
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE ref_statuses IS 'Справочник статусов компаний (Действующий, Ликвидирован и т.д.)';
COMMENT ON COLUMN ref_statuses.id IS 'Код состояния из ЕГР (nksost)';
COMMENT ON COLUMN ref_statuses.name IS 'Наименование статуса (vnsostk)';

-- 2. Справочник способов создания
-- Источник: nsi00208 в JSON
CREATE TABLE IF NOT EXISTS ref_creation_methods (
    id INTEGER PRIMARY KEY,        -- nkscrt (Код способа)
    name TEXT NOT NULL,            -- vnscrtp (Наименование)
    system_id INTEGER,             -- nsi00208 (ID справочника ЕГР)
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE ref_creation_methods IS 'Справочник способов создания компаний';
COMMENT ON COLUMN ref_creation_methods.id IS 'Код способа создания (nkscrt)';
COMMENT ON COLUMN ref_creation_methods.name IS 'Наименование способа (vnscrtp)';

-- 3. Справочник видов объектов (ЮЛ/ИП)
-- Источник: nsi00211 в JSON
CREATE TABLE IF NOT EXISTS ref_entity_types (
    id INTEGER PRIMARY KEY,        -- nkvob (Код вида)
    name TEXT NOT NULL,            -- vnvobp (Наименование)
    system_id INTEGER,             -- nsi00211 (ID справочника ЕГР)
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE ref_entity_types IS 'Справочник видов объектов (Юридическое лицо, Индивидуальный предприниматель)';
COMMENT ON COLUMN ref_entity_types.id IS 'Код вида объекта (nkvob)';
COMMENT ON COLUMN ref_entity_types.name IS 'Наименование вида (vnvobp)';

-- 4. Справочник органов (Исполкомы, Министерства)
-- Источник: nsi00212, nsi00212CRT, nsi00212LKV в JSON
-- Этот справочник общий для current_authority, creation и liquidation
CREATE TABLE IF NOT EXISTS ref_authorities (
    id INTEGER PRIMARY KEY,        -- nkuz (Код узла)
    name TEXT NOT NULL,            -- vnuzp (Наименование)
    system_id INTEGER,             -- nsi00212 (ID справочника ЕГР)
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE ref_authorities IS 'Справочник регистрирующих органов (Исполкомы, Министерства)';
COMMENT ON COLUMN ref_authorities.id IS 'Код органа (nkuz)';
COMMENT ON COLUMN ref_authorities.name IS 'Наименование органа (vnuzp)';

-- 5. Справочник способов исключения/ликвидации
-- Источник: nsi00228 в JSON
CREATE TABLE IF NOT EXISTS ref_liquidation_methods (
    id INTEGER PRIMARY KEY,        -- nkslkv (Код способа)
    name TEXT NOT NULL,            -- vnslkvp (Наименование)
    system_id INTEGER,             -- nsi00228 (ID справочника ЕГР)
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE ref_liquidation_methods IS 'Справочник способов ликвидации компаний';
COMMENT ON COLUMN ref_liquidation_methods.id IS 'Код способа ликвидации (nkslkv)';
COMMENT ON COLUMN ref_liquidation_methods.name IS 'Наименование способа (vnslkvp)';

-- Создаем индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_ref_statuses_name ON ref_statuses(name);
CREATE INDEX IF NOT EXISTS idx_ref_creation_methods_name ON ref_creation_methods(name);
CREATE INDEX IF NOT EXISTS idx_ref_entity_types_name ON ref_entity_types(name);
CREATE INDEX IF NOT EXISTS idx_ref_authorities_name ON ref_authorities(name);
CREATE INDEX IF NOT EXISTS idx_ref_liquidation_methods_name ON ref_liquidation_methods(name);

-- Триггеры для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_ref_statuses_updated_at BEFORE UPDATE ON ref_statuses 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_ref_creation_methods_updated_at BEFORE UPDATE ON ref_creation_methods 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_ref_entity_types_updated_at BEFORE UPDATE ON ref_entity_types 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_ref_authorities_updated_at BEFORE UPDATE ON ref_authorities 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_ref_liquidation_methods_updated_at BEFORE UPDATE ON ref_liquidation_methods 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();





