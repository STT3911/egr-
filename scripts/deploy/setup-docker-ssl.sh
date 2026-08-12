#!/bin/bash
# Issue/renew the production certificate for company.tenders.by and switch the
# Docker deployment to the new public URL. Run from the repository root.

set -euo pipefail

DOMAIN="${DOMAIN:-company.tenders.by}"
LEGACY_DOMAIN="${LEGACY_DOMAIN:-test.tendex.by}"
EMAIL="${EMAIL:-admin@tendex.by}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
CERT_DIR="/etc/letsencrypt/live/$DOMAIN"

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  echo "Run with sudo: sudo bash scripts/deploy/setup-docker-ssl.sh"
  exit 1
fi

cd "$PROJECT_DIR"

upsert_env() {
  key="$1"
  value="$2"
  touch "$ENV_FILE"
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

echo "Checking DNS for $DOMAIN..."
domain_ip="$(getent ahostsv4 "$DOMAIN" | awk 'NR == 1 { print $1 }')"
public_ip="$(curl -4fsS --max-time 10 https://api.ipify.org || true)"
if [ -z "$domain_ip" ]; then
  echo "No A record found for $DOMAIN"
  exit 1
fi
if [ -n "$public_ip" ] && [ "$domain_ip" != "$public_ip" ]; then
  echo "$DOMAIN resolves to $domain_ip, but this server reports $public_ip"
  exit 1
fi

if ! command -v certbot >/dev/null 2>&1; then
  apt-get update
  apt-get install -y certbot
fi

# Port 80 is published by the Docker nginx container. Stop only that service;
# the API, workers and database remain running while certbot uses standalone.
docker compose stop egr-nginx
restore_nginx() {
  docker compose up -d egr-nginx >/dev/null 2>&1 || true
}
trap restore_nginx EXIT

cert_args=(
  certonly --standalone --non-interactive --agree-tos
  --email "$EMAIL"
  --cert-name "$DOMAIN"
  --domain "$DOMAIN"
)

# Keep the previous public URL valid long enough to return a clean 301 redirect.
if getent ahostsv4 "$LEGACY_DOMAIN" >/dev/null 2>&1; then
  cert_args+=(--domain "$LEGACY_DOMAIN")
fi

certbot "${cert_args[@]}"

install -d -m 0755 "$PROJECT_DIR/ssl"
install -m 0644 "$CERT_DIR/fullchain.pem" "$PROJECT_DIR/ssl/fullchain.pem"
install -m 0600 "$CERT_DIR/privkey.pem" "$PROJECT_DIR/ssl/privkey.pem"

upsert_env APP_URL "https://$DOMAIN"
upsert_env TENDEX_API_URL "https://$DOMAIN"
upsert_env ALLOWED_HOSTS "$DOMAIN,$LEGACY_DOMAIN,localhost,127.0.0.1,egr-api,egr_api"
upsert_env CORS_ORIGINS "https://$DOMAIN,https://$LEGACY_DOMAIN"
upsert_env LETSENCRYPT_LIVE "$CERT_DIR"

docker compose up -d --build --force-recreate frontend egr-api egr-celery-worker egr-nginx
trap - EXIT

docker compose exec -T egr-nginx nginx -t
curl -fsS --max-time 20 "https://$DOMAIN/health" >/dev/null

cat >/etc/cron.d/tendex-cert-renew <<EOF
17 3 * * * root certbot renew --quiet --cert-name $DOMAIN --pre-hook 'cd $PROJECT_DIR && docker compose stop egr-nginx' --deploy-hook 'install -m 0644 $CERT_DIR/fullchain.pem $PROJECT_DIR/ssl/fullchain.pem && install -m 0600 $CERT_DIR/privkey.pem $PROJECT_DIR/ssl/privkey.pem' --post-hook 'cd $PROJECT_DIR && docker compose up -d egr-nginx'
EOF
chmod 0644 /etc/cron.d/tendex-cert-renew

echo "Domain migration complete: https://$DOMAIN"
