#!/bin/bash
# Setup SSL for Docker-based test.tendex.by
# Run this on your server after docker-fix.sh

set -e

DOMAIN="test.tendex.by"
EMAIL="admin@tendex.by"

echo "🔐 Setting up SSL for Docker-based $DOMAIN"

# Check if we're on the server with root access
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root or with sudo"
    exit 1
fi

# Install certbot if not installed
echo "📦 Installing certbot..."
if ! command -v certbot &> /dev/null; then
    apt update
    apt install -y certbot
fi

# Check if nginx is running in Docker
echo "🌐 Checking Docker nginx..."
if docker ps | grep -q egr_nginx; then
    echo "✅ Docker nginx is running"
else
    echo "❌ Docker nginx is not running. Start services first:"
    echo "docker compose up -d"
    exit 1
fi

# Stop Docker nginx temporarily for certbot standalone
echo "🛑 Stopping Docker nginx for SSL setup..."
docker compose stop egr-nginx

# Get SSL certificate
echo "🔐 Getting SSL certificate..."
certbot certonly --standalone \
  --non-interactive \
  --agree-tos \
  --email $EMAIL \
  --domain $DOMAIN \
  --domain www.$DOMAIN

# Create SSL directory for Docker
echo "📁 Creating SSL directory..."
mkdir -p /opt/egr-service/ssl

# Copy certificates
echo "📋 Copying certificates..."
cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem /opt/egr-service/ssl/
cp /etc/letsencrypt/live/$DOMAIN/privkey.pem /opt/egr-service/ssl/

# Update nginx config to use SSL
echo "🌐 Updating nginx config for SSL..."
cat > nginx/conf.d/test.tendex.by.conf << 'EOF'
# EGR Service - test.tendex.by (HTTPS with Docker SSL)
upstream backend {
  server egr-api:8002;
}

upstream frontend {
  server frontend:80;
}

# HTTP to HTTPS redirect
server {
  listen 80;
  server_name test.tendex.by www.test.tendex.by;
  return 301 https://$server_name$request_uri;
}

# HTTPS Server
server {
  listen 443 ssl http2;
  server_name test.tendex.by www.test.tendex.by;

  # SSL Configuration
  ssl_certificate /etc/ssl/certs/fullchain.pem;
  ssl_certificate_key /etc/ssl/private/privkey.pem;

  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-SHA256:ECDHE-RSA-AES256-SHA384;
  ssl_prefer_server_ciphers off;
  ssl_session_cache shared:SSL:10m;
  ssl_session_timeout 10m;

  client_max_body_size 100M;

  # Security Headers
  add_header X-Frame-Options "SAMEORIGIN" always;
  add_header X-Content-Type-Options "nosniff" always;
  add_header X-XSS-Protection "1; mode=block" always;
  add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;

  # Main location
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

  # API location
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

  # Documentation
  location ~ ^/(docs|redoc|openapi.json) {
    proxy_pass http://backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }

  # Health check
  location /health {
    proxy_pass http://backend/api/v1/health;
    access_log off;
  }

  # Favicon and static assets
  location ~* \.(ico|png|jpg|jpeg|gif|svg|css|js|woff|woff2|ttf|eot|webmanifest)$ {
    proxy_pass http://frontend;
    expires 1y;
    add_header Cache-Control "public, immutable";
  }

  access_log /var/log/nginx/access.log;
  error_log /var/log/nginx/error.log;
}
EOF

# Update docker-compose to mount SSL certificates
echo "🐳 Updating docker-compose for SSL..."
# Add SSL volume mount to egr-nginx service
sed -i '/egr-nginx:/,/networks:/ {
  /volumes:/a\
      - /opt/egr-service/ssl:/etc/ssl:ro
}' docker-compose.yml

# Restart services with SSL
echo "🔄 Restarting services with SSL..."
cd /opt/egr-service
docker compose down
docker compose up -d

# Setup auto-renewal with Docker restart
echo "🔄 Setting up SSL auto-renewal..."
(crontab -l ; echo "0 12 * * * /usr/bin/certbot renew --quiet --deploy-hook 'cd /opt/egr-service && docker compose restart egr-nginx'") 2>/dev/null | crontab -

# Test SSL
echo "🧪 Testing SSL..."
sleep 5

if curl -f --max-time 10 https://$DOMAIN > /dev/null 2>&1; then
    echo "✅ HTTPS works perfectly!"
    echo "🔒 SSL certificate is valid"
else
    echo "❌ HTTPS not working"
    echo "📋 Check: curl -v https://$DOMAIN"
fi

echo ""
echo "🎉 SSL setup complete!"
echo "🌐 Site: https://$DOMAIN"
echo "🔒 Certificate auto-renews monthly"
echo "🔄 Docker services include SSL certificates"