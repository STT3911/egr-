#!/bin/bash
set -e

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-postgres}"

echo "╔════════════════════════════════════════════════════════╗"
echo "║         INITIAL DATA IMPORT - Starting...              ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# Wait for database
echo "🔍 Waiting for database to be ready..."
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER"; do
  echo "⏳ Database is unavailable - sleeping"
  sleep 2
done

echo "✅ Database is ready!"
echo ""

# Wait for migrations to complete (wait for API to finish migrations)
echo "⏳ Waiting for migrations to complete..."
sleep 10

# Run auto-import
echo "🚀 Starting automatic data import..."
python3 /app/scripts/legacy/auto_import_data.py

if [ $? -eq 0 ]; then
    echo ""
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║         ✅ INITIAL DATA IMPORT - Complete!            ║"
    echo "╚════════════════════════════════════════════════════════╝"
    exit 0
else
    echo ""
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║         ❌ INITIAL DATA IMPORT - Failed!              ║"
    echo "╚════════════════════════════════════════════════════════╝"
    exit 1
fi
