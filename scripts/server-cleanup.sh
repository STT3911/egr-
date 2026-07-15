#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${EGR_BACKUP_DIR:-/home/user/egr-backups}"
DRY_RUN=false

if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=true
elif [ "$#" -gt 0 ]; then
  echo "Usage: $0 [--dry-run]" >&2
  exit 2
fi

run() {
  if "$DRY_RUN"; then
    printf 'DRY RUN:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

cleanup_backups() {
  [ -d "$BACKUP_DIR" ] || return 0

  local latest
  latest="$(
    find "$BACKUP_DIR" -maxdepth 1 -type f -name 'egr_db_*.sql.gz' \
      -printf '%T@ %p\n' | sort -nr | sed -n '1s/^[^ ]* //p'
  )"
  [ -n "$latest" ] || return 0

  if ! gzip -t "$latest"; then
    echo "ERROR: latest backup is corrupted; old backups were not removed: $latest" >&2
    return 1
  fi

  while IFS= read -r -d '' backup; do
    [ "$backup" = "$latest" ] || run rm -f -- "$backup"
  done < <(
    find "$BACKUP_DIR" -maxdepth 1 -type f -name 'egr_db_*.sql.gz' -print0
  )
  echo "Latest database backup preserved: $latest"
}

cleanup_container_logs() {
  local container_id log_path log_size
  while IFS= read -r container_id; do
    [ -n "$container_id" ] || continue
    log_path="$(docker inspect --format '{{.LogPath}}' "$container_id" 2>/dev/null || true)"
    [ -n "$log_path" ] && [ -f "$log_path" ] || continue
    log_size="$(stat -c '%s' "$log_path" 2>/dev/null || echo 0)"
    [ "$log_size" -gt 0 ] || continue

    if [ -w "$log_path" ]; then
      run truncate -s 0 "$log_path"
    elif [ "${EUID:-$(id -u)}" -eq 0 ]; then
      run truncate -s 0 "$log_path"
    elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
      run sudo truncate -s 0 "$log_path"
    else
      echo "Skipped Docker log without write permission: $log_path" >&2
    fi
  done < <(docker ps -aq)
}

echo "Database volumes are protected: this script never removes Docker volumes."
echo "Disk usage before cleanup:"
df -h /
docker system df || true

cleanup_backups
cleanup_container_logs
run docker builder prune --all --force
run docker image prune --all --force

echo "Disk usage after cleanup:"
df -h /
docker system df || true
