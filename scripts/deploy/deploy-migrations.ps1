# Deploy EGR Service migrations to server
# Usage: .\deploy-migrations.ps1

$SERVER = "user@188.130.170.42"
$PORT = "22"
$REMOTE_PATH = "~/egr/migrations/versions"

Write-Host "🚀 Deploying migration fixes to server..." -ForegroundColor Cyan

# 1. Remove old/conflicting migrations from server
Write-Host "`n📌 Removing old migration files from server..." -ForegroundColor Yellow
ssh -p $PORT $SERVER "rm -f $REMOTE_PATH/78663ebe9c1d_add_creation_and_entity_type_fields_to_.py"
ssh -p $PORT $SERVER "rm -f $REMOTE_PATH/8e60087850a2_add_current_name_and_address_to_.py"
ssh -p $PORT $SERVER "rm -f $REMOTE_PATH/09189a1fc7ba_add_egr_events_table.py"
ssh -p $PORT $SERVER "rm -f $REMOTE_PATH/a1b2c3d4e5f6_add_company_fields_and_events_table.py"

# 2. Copy new migration file
Write-Host "`n📌 Copying new migration file..." -ForegroundColor Yellow
scp -P $PORT "migrations/versions/b2c3d4e5f6g7_add_missing_reference_tables_and_events.py" "${SERVER}:${REMOTE_PATH}/"

# 3. Restart egr-api container to apply migrations
Write-Host "`n📌 Restarting egr-api container to apply migrations..." -ForegroundColor Yellow
ssh -p $PORT $SERVER "cd ~/egr && docker compose restart egr-api"

Write-Host "`n✅ Migration deployment complete!" -ForegroundColor Green
Write-Host "`n📊 Checking migration status..." -ForegroundColor Cyan
ssh -p $PORT $SERVER "cd ~/egr && docker compose logs egr-api --tail=50 | grep -i 'migration\|alembic'"

Write-Host "`n🔍 Verifying database tables..." -ForegroundColor Cyan
ssh -p $PORT $SERVER "docker compose exec db psql -U postgres -d egr_db -c '\dt' | grep -E 'ref_|egr_company_events'"

Write-Host "`nDone! Check the output above to verify all tables were created." -ForegroundColor Green


