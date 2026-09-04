#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERTBOT_IMAGE="${CERTBOT_IMAGE:-certbot/certbot:latest}"

mkdir -p "$ROOT_DIR/acme-webroot/.well-known/acme-challenge" "$ROOT_DIR/ssl"

docker run --rm \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -v "$ROOT_DIR/acme-webroot:/var/www/acme" \
  "$CERTBOT_IMAGE" renew --webroot --webroot-path /var/www/acme --quiet

docker run --rm \
  -v /etc/letsencrypt:/source:ro \
  -v "$ROOT_DIR/ssl:/dest" \
  alpine:3.19 sh -c \
  'cp -L /source/live/company.tenders.by/fullchain.pem /dest/fullchain.pem && cp -L /source/live/company.tenders.by/privkey.pem /dest/privkey.pem && chmod 644 /dest/*.pem'

cd "$ROOT_DIR"
docker compose exec -T egr-nginx nginx -t
docker compose exec -T egr-nginx nginx -s reload
