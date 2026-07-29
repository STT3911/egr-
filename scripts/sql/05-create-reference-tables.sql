-- Create missing reference tables

-- 6. ref_ved
CREATE TABLE IF NOT EXISTS ref_ved (
    id INTEGER PRIMARY KEY,
    code VARCHAR,
    name VARCHAR NOT NULL,
    system_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ref_ved_code ON ref_ved(code);
CREATE INDEX IF NOT EXISTS idx_ref_ved_name ON ref_ved(name);

-- 7. ref_countries
CREATE TABLE IF NOT EXISTS ref_countries (
    id INTEGER PRIMARY KEY,
    code INTEGER,
    name VARCHAR NOT NULL,
    system_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ref_countries_name ON ref_countries(name);

-- 8. ref_soato
CREATE TABLE IF NOT EXISTS ref_soato (
    id BIGINT PRIMARY KEY,
    code BIGINT,
    name VARCHAR NOT NULL,
    object_number INTEGER,
    system_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ref_soato_code ON ref_soato(code);
CREATE INDEX IF NOT EXISTS idx_ref_soato_name ON ref_soato(name);

-- 9. ref_foundations
CREATE TABLE IF NOT EXISTS ref_foundations (
    id INTEGER PRIMARY KEY,
    code INTEGER,
    name VARCHAR NOT NULL,
    system_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ref_foundations_name ON ref_foundations(name);

-- 10. ref_events
CREATE TABLE IF NOT EXISTS ref_events (
    id INTEGER PRIMARY KEY,
    code INTEGER,
    name VARCHAR NOT NULL,
    system_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ref_events_name ON ref_events(name);

-- 11. ref_street_types
CREATE TABLE IF NOT EXISTS ref_street_types (
    id INTEGER PRIMARY KEY,
    code INTEGER,
    name VARCHAR NOT NULL,
    system_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ref_street_types_name ON ref_street_types(name);

-- 12. ref_room_types
CREATE TABLE IF NOT EXISTS ref_room_types (
    id INTEGER PRIMARY KEY,
    code INTEGER,
    name VARCHAR NOT NULL,
    system_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ref_room_types_name ON ref_room_types(name);

-- 13. ref_room_categories
CREATE TABLE IF NOT EXISTS ref_room_categories (
    id INTEGER PRIMARY KEY,
    code INTEGER,
    name VARCHAR NOT NULL,
    system_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ref_room_categories_name ON ref_room_categories(name);

-- 14. ref_settlement_types
CREATE TABLE IF NOT EXISTS ref_settlement_types (
    id INTEGER PRIMARY KEY,
    code INTEGER,
    name VARCHAR NOT NULL,
    system_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ref_settlement_types_name ON ref_settlement_types(name);

-- 15. ref_document_types
CREATE TABLE IF NOT EXISTS ref_document_types (
    id INTEGER PRIMARY KEY,
    code INTEGER,
    name VARCHAR NOT NULL,
    system_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ref_document_types_name ON ref_document_types(name);

-- 16. ref_currencies
CREATE TABLE IF NOT EXISTS ref_currencies (
    id INTEGER PRIMARY KEY,
    code INTEGER,
    name VARCHAR NOT NULL,
    system_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ref_currencies_name ON ref_currencies(name);

-- 17. ref_positions
CREATE TABLE IF NOT EXISTS ref_positions (
    id INTEGER PRIMARY KEY,
    code INTEGER,
    name VARCHAR NOT NULL,
    system_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ref_positions_name ON ref_positions(name);

-- 18. ref_opf
CREATE TABLE IF NOT EXISTS ref_opf (
    id INTEGER PRIMARY KEY,
    code INTEGER,
    name VARCHAR NOT NULL,
    system_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ref_opf_name ON ref_opf(name);

-- Add new columns to egr_companies if they don't exist
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='egr_companies' AND column_name='creation_method_id') THEN
        ALTER TABLE egr_companies ADD COLUMN creation_method_id INTEGER;
        ALTER TABLE egr_companies ADD CONSTRAINT fk_egr_companies_creation_method_id 
            FOREIGN KEY (creation_method_id) REFERENCES ref_creation_methods(id);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='egr_companies' AND column_name='creation_decision_no') THEN
        ALTER TABLE egr_companies ADD COLUMN creation_decision_no VARCHAR;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='egr_companies' AND column_name='creation_authority_id') THEN
        ALTER TABLE egr_companies ADD COLUMN creation_authority_id INTEGER;
        ALTER TABLE egr_companies ADD CONSTRAINT fk_egr_companies_creation_authority_id 
            FOREIGN KEY (creation_authority_id) REFERENCES ref_authorities(id);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='egr_companies' AND column_name='current_authority_id') THEN
        ALTER TABLE egr_companies ADD COLUMN current_authority_id INTEGER;
        ALTER TABLE egr_companies ADD CONSTRAINT fk_egr_companies_current_authority_id 
            FOREIGN KEY (current_authority_id) REFERENCES ref_authorities(id);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='egr_companies' AND column_name='entity_type_id') THEN
        ALTER TABLE egr_companies ADD COLUMN entity_type_id INTEGER;
        ALTER TABLE egr_companies ADD CONSTRAINT fk_egr_companies_entity_type_id 
            FOREIGN KEY (entity_type_id) REFERENCES ref_entity_types(id);
    END IF;
END $$;

-- Create egr_company_events table
CREATE TABLE IF NOT EXISTS egr_company_events (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL REFERENCES egr_companies(id) ON DELETE CASCADE,
    event_record_id INTEGER,
    event_type_id INTEGER REFERENCES ref_events(id),
    event_date DATE,
    cancel_date DATE,
    document_date DATE,
    document_number VARCHAR,
    decision_authority_id INTEGER REFERENCES ref_authorities(id),
    document_authority_id INTEGER REFERENCES ref_authorities(id),
    foundation_id INTEGER REFERENCES ref_foundations(id),
    deadline_date DATE,
    suspension_end_date DATE,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_egr_company_events_company_id ON egr_company_events(company_id);
CREATE INDEX IF NOT EXISTS idx_egr_company_events_event_type_id ON egr_company_events(event_type_id);
CREATE INDEX IF NOT EXISTS idx_egr_company_events_event_date ON egr_company_events(event_date);
