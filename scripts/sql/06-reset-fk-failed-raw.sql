-- Сбросить last_error у записей, упавших из-за FK (справочники пусты), чтобы парсер подхватил их снова.
-- Запускать после заполнения справочников (update_reference_tables).

UPDATE egr_raw_company_data
SET last_error = NULL,
    processed_at = NULL
WHERE last_error IS NOT NULL
  AND (
    last_error LIKE '%ForeignKeyViolation%'
    OR last_error LIKE '%ref_creation_methods%'
    OR last_error LIKE '%ref_entity_types%'
    OR last_error LIKE '%ref_authorities%'
    OR last_error LIKE '%ref_statuses%'
    OR last_error LIKE '%ref_liquidation_methods%'
  );
