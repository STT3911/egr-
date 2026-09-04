#!/usr/bin/env bash
#
# Ежедневный бэкап БД egr_db без автоматического удаления старых копий.
# Запуск вручную:  ~/egr/scripts/db-backup.sh
# Cron (пример):   30 3 * * * /home/user/egr/scripts/db-backup.sh >> /home/user/egr-backups/backup.log 2>&1
#
set -euo pipefail

BACKUP_DIR="${EGR_BACKUP_DIR:-/home/user/egr-backups}"
DB_CONTAINER="${EGR_DB_CONTAINER:-egr_db}"
DB_USER="${EGR_DB_USER:-postgres}"
DB_NAME="${EGR_DB_NAME:-egr_db}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
FILE="$BACKUP_DIR/egr_db_${STAMP}.sql.gz"
TEMP_FILE="${FILE}.tmp"

cleanup_temp() {
  rm -f -- "$TEMP_FILE"
}
trap cleanup_temp EXIT

# pg_dump внутри контейнера → gzip на хосте
docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$TEMP_FILE"

# Проверяем архив до публикации нового бэкапа.
if [ ! -s "$TEMP_FILE" ] || ! gzip -t "$TEMP_FILE"; then
  echo "$(date '+%F %T') ERROR: backup is empty or corrupted: $TEMP_FILE" >&2
  exit 1
fi

mv -- "$TEMP_FILE" "$FILE"

echo "$(date '+%F %T') backup ok: $FILE ($(du -h "$FILE" | cut -f1))"
