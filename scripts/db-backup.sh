#!/usr/bin/env bash
#
# Ежедневный бэкап БД egr_db с ротацией.
# Запуск вручную:  ~/egr/scripts/db-backup.sh
# Cron (пример):   30 3 * * * /home/user/egr/scripts/db-backup.sh >> /home/user/egr-backups/backup.log 2>&1
#
set -euo pipefail

BACKUP_DIR="${EGR_BACKUP_DIR:-/home/user/egr-backups}"
RETENTION_DAYS="${EGR_BACKUP_RETENTION_DAYS:-14}"
DB_CONTAINER="${EGR_DB_CONTAINER:-egr_db}"
DB_USER="${EGR_DB_USER:-postgres}"
DB_NAME="${EGR_DB_NAME:-egr_db}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
FILE="$BACKUP_DIR/egr_db_${STAMP}.sql.gz"

# pg_dump внутри контейнера → gzip на хосте
docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$FILE"

# Проверка, что файл не пустой (на случай сбоя pg_dump)
if [ ! -s "$FILE" ]; then
  echo "$(date '+%F %T') ERROR: backup file is empty, removing: $FILE" >&2
  rm -f "$FILE"
  exit 1
fi

# Ротация: удалить бэкапы старше RETENTION_DAYS
find "$BACKUP_DIR" -name 'egr_db_*.sql.gz' -mtime +"$RETENTION_DAYS" -delete

echo "$(date '+%F %T') backup ok: $FILE ($(du -h "$FILE" | cut -f1))"
