#!/bin/bash
# Deploy missing tables fix to server

echo "🚀 Deploying database fixes to server..."

# Copy SQL file to container
echo "📋 Copying SQL file to database container..."
docker cp /home/user/egr/create_missing_tables.sql egr_db:/tmp/create_missing_tables.sql

# Execute SQL
echo "⚙️  Executing SQL to create missing tables..."
docker compose exec db psql -U postgres -d egr_db -f /tmp/create_missing_tables.sql

# Verify tables
echo ""
echo "✅ Verification: Checking reference tables..."
docker compose exec db psql -U postgres -d egr_db -c "SELECT COUNT(*) as ref_tables_count FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'ref_%';"

echo ""
echo "📊 All reference tables:"
docker compose exec db psql -U postgres -d egr_db -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'ref_%' ORDER BY tablename;"

echo ""
echo "🔍 Checking egr_company_events table..."
docker compose exec db psql -U postgres -d egr_db -c "SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'egr_company_events') as events_table_exists;"

echo ""
echo "🔍 Checking new columns in egr_companies..."
docker compose exec db psql -U postgres -d egr_db -c "\d egr_companies" | grep -E "creation_|entity_type_id"

echo ""
echo "✅ Done! All tables should be created."


