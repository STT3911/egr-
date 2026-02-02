# Init scripts (run automatically)

These scripts run **automatically** when the API container starts (see `docker-entrypoint.sh`).

## Flow

1. **docker-entrypoint.sh** (API container):
   - Waits for DB
   - Runs `alembic upgrade head`
   - Runs **scripts/init/run_sql_and_monitoring.sh**
   - Starts uvicorn

2. **run_sql_and_monitoring.sh**:
   - Runs all `scripts/sql/*.sql` in alphabetical order:
     - `00-add-search-name-column.sql` – add search_name column if missing
     - `01-pg_trgm.sql` – pg_trgm extension for fuzzy search
     - `02-create-indexes.sql` – indexes for companies and names
     - `03-populate-search-name.sql` – fill search_name for existing rows
     - `04-create-trigger.sql` – trigger for auto-filling search_name
     - `init-db.sql` – optional (can be empty)
   - Runs all `scripts/monitoring/*.sql` (diagnostic queries, log only):
     - `check_indexes.sql`
     - `check_performance.sql`

Logs are written to `/tmp/init-sql.log` inside the container.

## Manual run

From project root (e.g. on host or in another container):

```bash
# With env vars set (e.g. from .env)
export PGPASSWORD="$DB_PASSWORD"
for f in scripts/sql/*.sql; do
  psql -h "${DB_HOST:-db}" -p "${DB_PORT:-5432}" -U "${DB_USER:-postgres}" -d "${DB_NAME:-egr_db}" -f "$f"
done
```

Or inside API container:

```bash
docker compose exec egr-api bash /app/scripts/init/run_sql_and_monitoring.sh
```
