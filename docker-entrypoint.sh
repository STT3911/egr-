#!/bin/bash
set -e

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-postgres}"

echo "🔍 Waiting for database to be ready..."
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER"; do
  echo "⏳ Database is unavailable - sleeping"
  sleep 2
done

echo "✅ Database is ready!"
echo "🔄 Running database migrations..."
alembic upgrade head

echo "🚀 Starting application..."
exec "$@"
#!/bin/bash
set -e

echo "🔍 Waiting for database to be ready..."

# Wait for database
until pg_isready -h db -p 5432 -U postgres; do
  echo "⏳ Database is unavailable - sleeping"
  sleep 2
done

echo "✅ Database is ready!"

# Run migrations
echo "🔄 Running database migrations..."
alembic upgrade head

if [ $? -eq 0 ]; then
    echo "✅ Migrations completed successfully!"
else
    echo "❌ Migrations failed!"
    exit 1
fi

# Execute the main command
echo "🚀 Starting application..."
exec "$@"


