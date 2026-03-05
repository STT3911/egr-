    #!/bin/bash
# Run SQL migrations (scripts/sql) and monitoring scripts (scripts/monitoring) automatically.
# Called from docker-entrypoint.sh after alembic upgrade head.
set -e

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-egr_db}"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-postgres}"

export PGPASSWORD="$DB_PASSWORD"
SQL_DIR="/app/scripts/sql"
MONITORING_DIR="/app/scripts/monitoring"
LOG_FILE="/tmp/init-sql.log"

echo "Running SQL migrations from $SQL_DIR..."
for f in "$SQL_DIR"/*.sql; do
  if [ -f "$f" ]; then
    name=$(basename "$f")
    echo "  Executing: $name"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$f" >> "$LOG_FILE" 2>&1 || true
  fi
done

if [ -d "$MONITORING_DIR" ]; then
  echo "Running monitoring scripts from $MONITORING_DIR..."
  for f in "$MONITORING_DIR"/*.sql; do
    if [ -f "$f" ]; then
      name=$(basename "$f")
      echo "  Executing: $name"
      psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$f" >> "$LOG_FILE" 2>&1 || true
    fi
  done
fi

unset PGPASSWORD
echo "SQL and monitoring scripts completed. Log: $LOG_FILE"
