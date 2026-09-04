#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-admin@tendex.by}"
CERTBOT_IMAGE="${CERTBOT_IMAGE:-certbot/certbot:latest}"

mkdir -p "$ROOT_DIR/acme-webroot/.well-known/acme-challenge" "$ROOT_DIR/ssl"

if ! docker compose ps --status running --services | grep -qx 'egr-nginx'; then
  echo "ERROR: egr-nginx must be running before the ACME challenge" >&2
  exit 1
fi

docker run --rm \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -v "$ROOT_DIR/acme-webroot:/var/www/acme" \
  "$CERTBOT_IMAGE" certonly \
  --webroot --webroot-path /var/www/acme \
  --cert-name company.tenders.by \
  --domain company.tenders.by \
  --domain test.tendex.by \
  --email "$CERTBOT_EMAIL" \
  --agree-tos --non-interactive --expand --force-renewal

docker run --rm \
  -v /etc/letsencrypt:/source:ro \
  -v "$ROOT_DIR/ssl:/dest" \
  alpine:3.19 sh -c \
  'cp -L /source/live/company.tenders.by/fullchain.pem /dest/fullchain.pem && cp -L /source/live/company.tenders.by/privkey.pem /dest/privkey.pem && chmod 644 /dest/*.pem'

cd "$ROOT_DIR"
docker compose exec -T egr-nginx nginx -t
docker compose exec -T egr-nginx nginx -s reload

echo "Certificate installed for company.tenders.by and test.tendex.by"
