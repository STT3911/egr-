#!/bin/bash
set -e

echo "🔓 Disabling HTTPS (reverting to HTTP only)"
echo ""

if [ -f "nginx/conf.d/test.tendex.by.conf.backup" ]; then
    echo "📋 Restoring backup configuration..."
    cp nginx/conf.d/test.tendex.by.conf.backup nginx/conf.d/test.tendex.by.conf
    echo "✅ Backup restored"
else
    echo "⚠️  No backup found, creating HTTP-only config..."
    cat > nginx/conf.d/test.tendex.by.conf << 'EOF'
# EGR Service - test.tendex.by (HTTP Only)
upstream backend {
  server egr-api:8000;
}

upstream frontend {
  server frontend:80;
}

server {
  listen 80;
  server_name test.tendex.by _;

  client_max_body_size 100M;

  add_header X-Frame-Options "SAMEORIGIN" always;
  add_header X-Content-Type-Options "nosniff" always;
  add_header X-XSS-Protection "1; mode=block" always;

  location / {
    proxy_pass http://frontend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host $host;
    proxy_cache_bypass $http_upgrade;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }

  location /api {
    proxy_pass http://backend;
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
    proxy_pass http://backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }

  location /health {
    proxy_pass http://backend/api/v1/health;
    access_log off;
  }

  location ~* \.(jpg|jpeg|png|gif|ico|css|js|svg|woff|woff2|ttf|eot|webmanifest)$ {
    proxy_pass http://frontend;
    expires 1y;
    add_header Cache-Control "public, immutable";
  }

  access_log /var/log/nginx/access.log;
  error_log /var/log/nginx/error.log;
}
EOF
    echo "✅ HTTP-only config created"
fi

echo ""
echo "📋 Reloading nginx..."
docker compose exec egr-nginx nginx -t
docker compose exec egr-nginx nginx -s reload
echo "✅ Nginx reloaded"
echo ""
echo "🌐 Your site is now available at:"
echo "   http://test.tendex.by"
echo ""
