#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ "$(git branch --show-current)" != "develop" ]; then
  echo "ERROR: dev deployment must run from the develop branch" >&2
  exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: tracked working tree changes must be committed first" >&2
  exit 1
fi

if [ ! -f .env.dev ]; then
  echo "ERROR: $ROOT_DIR/.env.dev is missing" >&2
  exit 1
fi

git fetch origin develop
git pull --ff-only origin develop

COMPOSE=(docker compose --project-name egr-dev --env-file .env.dev -f deploy/dev/docker-compose.yml)
"${COMPOSE[@]}" config --quiet
"${COMPOSE[@]}" build api frontend
"${COMPOSE[@]}" up -d --wait db redis api frontend
"${COMPOSE[@]}" ps

docker exec egr_nginx wget -q -O /dev/null http://egr-dev-api:8000/api/v1/health/ready
docker exec egr_nginx wget -q -O /dev/null http://egr-dev-frontend/

echo "Dev containers are healthy. Verify https://test.tendex.by after the proxy and TLS changes are promoted to main."
