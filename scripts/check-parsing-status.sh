#!/bin/bash
# Диагностика: почему pending не уменьшается (0 processed).
# Запуск: из корня проекта или docker exec egr_db ...
# Использование: ./scripts/check-parsing-status.sh
# Или: docker exec egr_db psql -U postgres -d egr_db -f - < scripts/sql/check-parsing-status.sql

set -e
cd "$(dirname "$0")/.."

echo "=== 1. Счётчики egr_raw_company_data ==="
docker exec egr_db psql -U postgres -d egr_db -t -c "
  SELECT
    COUNT(*) FILTER (WHERE processed_at IS NULL) AS pending,
    COUNT(*) FILTER (WHERE processed_at IS NOT NULL) AS processed,
    COUNT(*) FILTER (WHERE last_error IS NOT NULL AND last_error != '') AS with_error
  FROM egr_raw_company_data;
"

echo ""
echo "=== 2. Примеры last_error (если парсинг падает) ==="
docker exec egr_db psql -U postgres -d egr_db -t -c "
  SELECT LEFT(last_error, 120) AS err_sample, COUNT(*) AS cnt
  FROM egr_raw_company_data
  WHERE last_error IS NOT NULL AND last_error != ''
  GROUP BY LEFT(last_error, 120)
  ORDER BY cnt DESC
  LIMIT 5;
"

echo ""
echo "=== 3. Справочники (ref_creation_methods и др.) — должны быть не пусты ==="
docker exec egr_db psql -U postgres -d egr_db -t -c "
  SELECT 'ref_creation_methods' AS tbl, COUNT(*) FROM ref_creation_methods
  UNION ALL SELECT 'ref_statuses', COUNT(*) FROM ref_statuses
  UNION ALL SELECT 'ref_opf', COUNT(*) FROM ref_opf
  UNION ALL SELECT 'ref_authorities', COUNT(*) FROM ref_authorities;
"

echo ""
echo "=== 4. Celery: worker и beat должны быть запущены ==="
echo "  docker compose ps egr-celery-worker egr-celery-beat"
docker compose ps egr-celery-worker egr-celery-beat 2>/dev/null || true

echo ""
echo "Логи воркера (последние ошибки парсинга):"
echo "  docker compose logs egr-celery-worker --tail 50"
echo ""
echo "Если везде last_error с ForeignKeyViolation / NotNullViolation — заполните справочники:"
echo "  docker compose exec egr-api python -c \"from app.tasks.sync_tasks import update_reference_tables; update_reference_tables.run()\""
echo "Или выполните SQL из scripts/sql/ (07-fill-missing-ref-placeholders.sql и т.д.)."
