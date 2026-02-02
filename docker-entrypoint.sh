#!/bin/bash
set -e

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-postgres}"

echo "Waiting for database to be ready..."
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER"; do
  echo "Database is unavailable - sleeping"
  sleep 2
done

echo "Database is ready."

# When egr-init has already run migrations and SQL (docker-compose), skip to save API startup time
if [ -n "$SKIP_SQL_INIT" ]; then
  echo "Migrations and SQL init done by egr-init — starting app."
  exec "$@"
fi

echo "Running database migrations..."
alembic upgrade head || echo "Migration failed, continuing anyway..."

if [ -f /app/scripts/init/run_sql_and_monitoring.sh ]; then
  echo "Running SQL and monitoring scripts..."
  bash /app/scripts/init/run_sql_and_monitoring.sh || echo "SQL scripts failed, continuing anyway..."
fi

echo "Starting application..."
exec "$@"
