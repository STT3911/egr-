#!/bin/bash
# Fill search_name for existing rows in egr_company_names_history.
# Safe to run multiple times (only updates NULL/empty search_name).
# Run from project root: ./scripts/fill-search-name.sh
set -e
cd "$(dirname "$0")/.."

echo "Filling search_name in egr_company_names_history..."
docker compose exec egr-api sh -c 'PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f /app/scripts/sql/03-populate-search-name.sql'
echo "Done."
echo "Alternative (Python): docker compose exec egr-api python /app/scripts/fill_search_names_python.py"
