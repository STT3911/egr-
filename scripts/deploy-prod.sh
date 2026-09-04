#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ "$(git branch --show-current)" != "main" ]; then
  echo "ERROR: production deployment must run from the main branch" >&2
  exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: tracked working tree changes must be committed first" >&2
  exit 1
fi

git fetch origin main
git pull --ff-only origin main

docker compose config --quiet
docker compose build egr-api egr-celery-worker egr-celery-worker-heavy egr-celery-worker-bankrot egr-celery-beat frontend
docker compose run --rm egr-api alembic upgrade head
docker compose up -d --wait egr-api egr-celery-worker egr-celery-worker-heavy egr-celery-worker-bankrot egr-celery-beat frontend egr-nginx
docker compose ps

curl -fsS https://company.tenders.by/api/v1/health/ready >/dev/null
echo "Production deployment is healthy: https://company.tenders.by"
