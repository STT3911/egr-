#!/bin/bash
# Setup SSL for Docker-based test.tendex.by
# Run this on your server after docker-fix.sh

set -e

DOMAIN="test.tendex.by"
EMAIL="admin@tendex.by"
PROJECT_DIR="$(pwd)"

echo "🔐 Setting up SSL for Docker-based $DOMAIN"
echo "📁 Working directory: $PROJECT_DIR"

# Check if we're on the server with root access
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root or with sudo"
    exit 1
fi

# Check if docker-compose.yml exists
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ docker-compose.yml not found!"
    echo "Please run this script from the project directory (e.g., /opt/egr-service or ~/egr)"
    exit 1
fi

# Install certbot if not installed
echo "📦 Installing certbot..."
if ! command -v certbot &> /dev/null; then
    apt update
    apt install -y certbot
fi

echo "🌐 Checking Docker nginx..."
if docker ps | grep -q egr_nginx; then
    echo "✅ Docker nginx is running"
    echo "🛑 Stopping Docker nginx for SSL setup..."
    docker compose stop egr-nginx
else
    echo "⚠️ Docker nginx is not running, continuing..."
fi
echo "🔐 Getting SSL certificate..."
echo "📋 Checking DNS for $DOMAIN..."
if nslookup $DOMAIN > /dev/null 2>&1; then
    echo "✅ DNS record found for $DOMAIN"
else
    echo "❌ DNS record not found for $DOMAIN"
    echo "Please add an A record pointing to this server's IP"
    exit 1
fi

certbot certonly --standalone \
  --non-interactive \
  --agree-tos \
  --email $EMAIL \
  --domain $DOMAIN || {
    echo "❌ SSL certificate failed. Check if:"
    echo "  - Port 80 is accessible from internet"
    echo "  - Domain $DOMAIN points to this server"
    echo "  - No other service is using port 80"
    echo ""
    echo "Debug commands:"
    echo "  nslookup $DOMAIN"
    echo "  curl -I http://$DOMAIN"
    exit 1
  }

echo "✅ SSL certificate obtained successfully!"

# Create SSL directory for Docker
echo "📁 Creating SSL directory..."
mkdir -p $PROJECT_DIR/ssl

# Copy certificates
echo "📋 Copying certificates..."
cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem $PROJECT_DIR/ssl/
cp /etc/letsencrypt/live/$DOMAIN/privkey.pem $PROJECT_DIR/ssl/
chmod 644 $PROJECT_DIR/ssl/*.pem

# Enable HTTPS in nginx config
echo "🌐 Enabling HTTPS in nginx config..."
sed -i 's/# return 301 https:/return 301 https:/g' nginx/conf.d/test.tendex.by.conf
sed -i 's/# server {/server {/g' nginx/conf.d/test.tendex.by.conf
sed -i 's/#   listen 443/  listen 443/g' nginx/conf.d/test.tendex.by.conf
sed -i 's/#   server_name/  server_name/g' nginx/conf.d/test.tendex.by.conf
sed -i 's/#   ssl/  ssl/g' nginx/conf.d/test.tendex.by.conf
sed -i 's/#   client/  client/g' nginx/conf.d/test.tendex.by.conf
sed -i 's/#   add_header/  add_header/g' nginx/conf.d/test.tendex.by.conf
sed -i 's/#   location/  location/g' nginx/conf.d/test.tendex.by.conf
sed -i 's/#   proxy/  proxy/g' nginx/conf.d/test.tendex.by.conf
sed -i 's/#   access_log/  access_log/g' nginx/conf.d/test.tendex.by.conf
sed -i 's/#   error_log/  error_log/g' nginx/conf.d/test.tendex.by.conf
sed -i 's/#   expires/  expires/g' nginx/conf.d/test.tendex.by.conf
sed -i 's/# }/}/g' nginx/conf.d/test.tendex.by.conf

# Create complete HTTPS config
cat > nginx/conf.d/test.tendex.by.conf << 'EOF'
# EGR Service - test.tendex.by (Docker with SSL)
upstream backend {
  server egr-api:8002;
}

upstream frontend {
  server frontend:80;
}

# HTTP to HTTPS redirect
server {
  listen 80;
  server_name test.tendex.by;
  return 301 https://$server_name$request_uri;
}

# HTTPS Server
server {
  listen 443 ssl http2;
  server_name test.tendex.by;

  # SSL Configuration
  ssl_certificate /etc/nginx/ssl/fullchain.pem;
  ssl_certificate_key /etc/nginx/ssl/privkey.pem;

  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
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

# Restart services with SSL
echo "🔄 Restarting services with SSL..."
docker compose down
docker compose up -d

# Wait for services
echo "⏳ Waiting for services to start..."
sleep 20

# Test local HTTPS
echo "🧪 Testing local services..."
if curl -f --max-time 10 http://localhost > /dev/null 2>&1; then
    echo "✅ Local HTTP works"
else
    echo "❌ Local HTTP failed"
    docker compose logs egr-nginx | tail -10
fi

# Test external HTTPS
echo "🌐 Testing external HTTPS..."
if curl -f -k --max-time 10 https://localhost > /dev/null 2>&1; then
    echo "✅ Local HTTPS works"
else
    echo "⚠️ Local HTTPS not working (normal if port 443 not exposed to localhost)"
fi

# Test external domain
if curl -f --max-time 10 https://$DOMAIN > /dev/null 2>&1; then
    echo "✅ External HTTPS works perfectly!"
    echo "🔒 SSL certificate is valid"
else
    echo "⚠️ External HTTPS not working yet. Checking HTTP..."
    if curl -f --max-time 10 http://$DOMAIN > /dev/null 2>&1; then
        echo "⚠️ HTTP works. HTTPS redirect may take a moment."
    else
        echo "❌ Site not accessible externally"
        echo "📋 Check DNS: nslookup $DOMAIN"
    fi
fi

# Setup auto-renewal with Docker restart
echo "🔄 Setting up SSL auto-renewal..."
(crontab -l 2>/dev/null | grep -v certbot; echo "0 12 * * * /usr/bin/certbot renew --quiet --deploy-hook 'cp /etc/letsencrypt/live/$DOMAIN/*.pem ${PROJECT_DIR}/ssl/ && cd ${PROJECT_DIR} && docker compose restart egr-nginx'") | crontab -

echo ""
echo "🎉 SSL setup complete!"
echo "🌐 Site: https://$DOMAIN"
echo "🔒 Certificate auto-renews monthly"
echo "🔄 Docker services include SSL certificates"
echo ""
echo "📋 Next steps:"
echo "  1. Check status: ./status.sh"
echo "  2. View logs: docker compose logs egr-nginx"
echo "  3. Test site: curl -I https://$DOMAIN"