#!/usr/bin/env bash
#
# Ежедневный бэкап БД egr_db. После проверки новой копии оставляем только её.
# Запуск вручную:  ~/egr/scripts/db-backup.sh
# Очистка без создания копии: ~/egr/scripts/db-backup.sh --prune-only
# Cron (пример):   30 3 * * * /home/user/egr/scripts/db-backup.sh >> /home/user/egr-backups/backup.log 2>&1
#
set -euo pipefail
umask 077

BACKUP_DIR="${EGR_BACKUP_DIR:-/home/user/egr-backups}"
DB_CONTAINER="${EGR_DB_CONTAINER:-egr_db}"
DB_USER="${EGR_DB_USER:-postgres}"
DB_NAME="${EGR_DB_NAME:-egr_db}"

PRUNE_ONLY=false
if [ "$#" -eq 1 ] && [ "$1" = "--prune-only" ]; then
  PRUNE_ONLY=true
elif [ "$#" -gt 0 ]; then
  echo "Usage: $0 [--prune-only]" >&2
  exit 2
fi

mkdir -p -- "$BACKUP_DIR"
BACKUP_DIR="$(cd -- "$BACKUP_DIR" && pwd -P)"

# Один замок для создания и очистки: параллельный запуск не трогает файлы.
exec 9>"$BACKUP_DIR/.db-backup.lock"
if ! flock -n 9; then
  echo "ERROR: another database backup or cleanup is running" >&2
  exit 1
fi

prune_old_backups() {
  local keep="${1:-}" backup
  local -a backups=()
  mapfile -d '' -t backups < <(
    find "$BACKUP_DIR" -maxdepth 1 -type f -regextype posix-extended \
      -regex '.*/egr_db_[0-9]{8}_[0-9]{6}\.sql\.gz' -printf '%f\0' \
      | LC_ALL=C sort -zr
  )
  if [ "${#backups[@]}" -eq 0 ]; then
    echo "No completed database backups to clean up"
    return
  fi

  # В режиме очистки выбираем по дате имени, а не по изменяемому mtime.
  # При обычном запуске keep — только что проверенная и опубликованная копия.
  if [ -z "$keep" ]; then
    keep="$BACKUP_DIR/${backups[0]}"
    if [ ! -s "$keep" ] || ! gzip -t -- "$keep"; then
      echo "ERROR: latest backup is empty or corrupted; old backups preserved: $keep" >&2
      return 1
    fi
  fi
  for backup in "${backups[@]}"; do
    backup="$BACKUP_DIR/$backup"
    if [ "$backup" != "$keep" ]; then
      rm -- "$backup"
      echo "Removed previous database backup: $backup"
    fi
  done
  echo "Database backup preserved: $keep"
}

if "$PRUNE_ONLY"; then
  prune_old_backups
  exit 0
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
FILE="$BACKUP_DIR/egr_db_${STAMP}.sql.gz"
TEMP_FILE="${FILE}.tmp"

# Не перезаписываем результат другого завершённого запуска той же секунды.
if [ -e "$FILE" ] || [ -e "$TEMP_FILE" ] || [ -L "$FILE" ] || [ -L "$TEMP_FILE" ]; then
  echo "ERROR: backup target already exists: $FILE" >&2
  exit 1
fi

cleanup_temp() {
  rm -f -- "$TEMP_FILE"
}
trap cleanup_temp EXIT

# pg_dump внутри контейнера → gzip на хосте
docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$TEMP_FILE"

# Проверяем архив до публикации нового бэкапа.
if [ ! -s "$TEMP_FILE" ] || ! gzip -t -- "$TEMP_FILE"; then
  echo "$(date '+%F %T') ERROR: backup is empty or corrupted: $TEMP_FILE" >&2
  exit 1
fi

mv -- "$TEMP_FILE" "$FILE"

echo "$(date '+%F %T') backup ok: $FILE ($(du -h "$FILE" | cut -f1))"
prune_old_backups "$FILE"
