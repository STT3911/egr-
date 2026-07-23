#!/bin/sh
# If SSL certs are missing, use HTTP-only config so nginx still starts.
# Used by egr-nginx when ./ssl is empty (e.g. first deploy before certbot).

set -e
MAIN_CONF=/etc/nginx/conf.d/test.tendex.by.conf
FALLBACK_CONF=/etc/nginx/conf.d/00-http-only-fallback.conf
SSL_CERT=/etc/nginx/ssl/fullchain.pem

if [ ! -f "$SSL_CERT" ]; then
  echo "No SSL cert at $SSL_CERT — enabling HTTP-only fallback."
  [ -f "$MAIN_CONF" ] && mv "$MAIN_CONF" "${MAIN_CONF}.disabled"
cat > "$FALLBACK_CONF" << 'NGINX_HTTP'
# EGR Service - HTTP only (SSL certs not yet present)
limit_req_zone $binary_remote_addr zone=api_per_ip:10m rate=80r/m;

server {
  listen 80;
  server_name test.tendex.by _;
  limit_req_status 429;
  resolver 127.0.0.11 valid=30s;
  client_max_body_size 100M;
  add_header X-Frame-Options "SAMEORIGIN" always;
  add_header X-Content-Type-Options "nosniff" always;

  location / {
    set $frontend_upstream http://frontend:80;
    proxy_pass $frontend_upstream;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
  location /api {
    limit_req zone=api_per_ip burst=80 nodelay;
    set $backend_upstream http://egr-api:8000;
    proxy_pass $backend_upstream;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 300s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;
  }
  location ~ ^/(docs|redoc|openapi.json) {
    set $backend_upstream http://egr-api:8000;
    proxy_pass $backend_upstream;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
  location /health {
    set $backend_upstream http://egr-api:8000;
    proxy_pass $backend_upstream/api/v1/health;
    access_log off;
  }
  location ~* \.(jpg|jpeg|png|gif|ico|css|js|svg|woff|woff2|ttf|eot|webmanifest)$ {
    set $frontend_upstream http://frontend:80;
    proxy_pass $frontend_upstream;
    expires 1y;
    add_header Cache-Control "public, immutable";
  }
  access_log /var/log/nginx/access.log;
  error_log /var/log/nginx/error.log;
}
NGINX_HTTP
else
  rm -f "$FALLBACK_CONF"
  [ -f "${MAIN_CONF}.disabled" ] && mv "${MAIN_CONF}.disabled" "$MAIN_CONF"
fi

exec "$@"
