-- Однократное заполнение ref_authorities с подстановкой имени при NULL (обход NOT NULL).
-- Запускать вручную (тяжёлый запрос по 1.6M строк): docker exec -i egr_db psql -U postgres -d egr_db < scripts/sql/manual/08-fill-ref-authorities-null-safe.sql
-- Не запускается при старте контейнера (файл в manual/).

INSERT INTO ref_authorities (id, name, system_id)
SELECT DISTINCT id, name, system_id FROM (
    SELECT
        ((data::jsonb->'base_info'->'nsi00212'->>'nkuz')::int) as id,
        COALESCE(NULLIF(TRIM(data::jsonb->'base_info'->'nsi00212'->>'vnuzp'), ''), 'Орган ' || ((data::jsonb->'base_info'->'nsi00212'->>'nkuz')::int)) as name,
        ((data::jsonb->'base_info'->'nsi00212'->>'nsi00212')::int) as system_id
    FROM egr_raw_company_data WHERE data::jsonb->'base_info'->'nsi00212' IS NOT NULL AND data::jsonb->'base_info'->'nsi00212'->>'nkuz' IS NOT NULL
    UNION ALL
    SELECT
        ((data::jsonb->'base_info'->'nsi00212CRT'->>'nkuz')::int) as id,
        COALESCE(NULLIF(TRIM(data::jsonb->'base_info'->'nsi00212CRT'->>'vnuzp'), ''), 'Орган ' || ((data::jsonb->'base_info'->'nsi00212CRT'->>'nkuz')::int)) as name,
        ((data::jsonb->'base_info'->'nsi00212CRT'->>'nsi00212')::int) as system_id
    FROM egr_raw_company_data WHERE data::jsonb->'base_info'->'nsi00212CRT' IS NOT NULL AND data::jsonb->'base_info'->'nsi00212CRT'->>'nkuz' IS NOT NULL
    UNION ALL
    SELECT
        ((data::jsonb->'base_info'->'nsi00212LKV'->>'nkuz')::int) as id,
        COALESCE(NULLIF(TRIM(data::jsonb->'base_info'->'nsi00212LKV'->>'vnuzp'), ''), 'Орган ' || ((data::jsonb->'base_info'->'nsi00212LKV'->>'nkuz')::int)) as name,
        ((data::jsonb->'base_info'->'nsi00212LKV'->>'nsi00212')::int) as system_id
    FROM egr_raw_company_data WHERE data::jsonb->'base_info'->'nsi00212LKV' IS NOT NULL AND data::jsonb->'base_info'->'nsi00212LKV'->>'nkuz' IS NOT NULL
) AS all_auths WHERE id IS NOT NULL
ON CONFLICT (id) DO UPDATE SET name = COALESCE(NULLIF(TRIM(EXCLUDED.name), ''), ref_authorities.name), updated_at = NOW();
