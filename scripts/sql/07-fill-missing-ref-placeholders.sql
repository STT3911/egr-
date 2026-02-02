-- Вставить недостающие строки в справочники (id 1..10), чтобы FK при парсинге не падал.
-- update_reference_tables заполняет справочники из raw_data; если путь в JSON другой — id может отсутствовать.
-- Запускать после 05-create-reference-tables.sql. ON CONFLICT DO NOTHING — не перезаписываем существующие.

INSERT INTO ref_creation_methods (id, name, system_id)
SELECT g.id, 'Способ создания ' || g.id, NULL
FROM generate_series(1, 10) AS g(id)
ON CONFLICT (id) DO NOTHING;

INSERT INTO ref_entity_types (id, name, system_id)
SELECT g.id, 'Тип объекта ' || g.id, NULL
FROM generate_series(1, 10) AS g(id)
ON CONFLICT (id) DO NOTHING;

INSERT INTO ref_statuses (id, name, system_id)
SELECT g.id, 'Статус ' || g.id, NULL
FROM generate_series(1, 10) AS g(id)
ON CONFLICT (id) DO NOTHING;

INSERT INTO ref_liquidation_methods (id, name, system_id)
SELECT g.id, 'Способ ликвидации ' || g.id, NULL
FROM generate_series(1, 10) AS g(id)
ON CONFLICT (id) DO NOTHING;
