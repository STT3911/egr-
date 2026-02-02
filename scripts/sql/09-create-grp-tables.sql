-- Таблицы ГРП (Государственный реестр плательщиков / данные налоговой).
-- Запуск: docker exec -i egr_db psql -U postgres -d egr_db < scripts/sql/09-create-grp-tables.sql

-- Сырые ответы API ГРП
CREATE TABLE IF NOT EXISTS grp_raw_data (
    unp BIGINT PRIMARY KEY,
    raw_json JSONB NOT NULL DEFAULT '{}',
    http_status INTEGER,
    last_error TEXT,
    fetched_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    parsed BOOLEAN DEFAULT FALSE,
    parsed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_grp_raw_unp ON grp_raw_data(unp);
CREATE INDEX IF NOT EXISTS idx_grp_raw_parsed ON grp_raw_data(parsed);

-- Распарсенные данные налогоплательщика
CREATE TABLE IF NOT EXISTS grp_taxpayer_data (
    unp BIGINT PRIMARY KEY,
    full_name VARCHAR,
    short_name VARCHAR,
    registration_date DATE,
    inspectorate_code VARCHAR,
    inspectorate_name VARCHAR,
    status_code VARCHAR,
    status_date DATE,
    address TEXT,
    fetched_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_grp_taxpayer_unp ON grp_taxpayer_data(unp);
