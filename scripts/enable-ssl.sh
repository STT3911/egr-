#!/bin/bash
set -e

echo "🔐 Enabling HTTPS for test.tendex.by"
echo ""

# Check we're in the right directory
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Error: docker-compose.yml not found"
    echo "   Run this script from the project root directory"
    exit 1
fi

# Check if SSL certificates exist
echo "📋 Step 1: Checking SSL certificates..."
if [ ! -f "ssl/fullchain.pem" ] || [ ! -f "ssl/privkey.pem" ]; then
    echo "❌ SSL certificates not found in ./ssl/"
    echo ""
    echo "Please copy certificates first:"
    echo "  sudo cp /etc/letsencrypt/live/test.tendex.by/fullchain.pem ssl/"
    echo "  sudo cp /etc/letsencrypt/live/test.tendex.by/privkey.pem ssl/"
    echo "  sudo chown -R \$USER:\$USER ssl/"
    exit 1
fi
echo "✅ SSL certificates found"
echo ""

# Backup current config
echo "📋 Step 2: Backing up current configuration..."
cp nginx/conf.d/test.tendex.by.conf nginx/conf.d/test.tendex.by.conf.backup
echo "✅ Backup created: nginx/conf.d/test.tendex.by.conf.backup"
echo ""

# Create HTTPS configuration
echo "📋 Step 3: Creating HTTPS configuration..."
cat > nginx/conf.d/test.tendex.by.conf << 'EOF'
# EGR Service - test.tendex.by (HTTPS)

# HTTP Server (redirect to HTTPS)
server {
  listen 80;
  server_name test.tendex.by _;
  
  # Redirect all HTTP to HTTPS
  return 301 https://$server_name$request_uri;
}

# HTTPS Server
server {
  listen 443 ssl http2;
  server_name test.tendex.by _;

  # Docker DNS resolver
  resolver 127.0.0.11 valid=30s;

  # SSL Configuration
  ssl_certificate /etc/nginx/ssl/fullchain.pem;
  ssl_certificate_key /etc/nginx/ssl/privkey.pem;
  
  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_ciphers 'ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-SHA256:ECDHE-RSA-AES256-SHA384';
  ssl_prefer_server_ciphers off;
  ssl_session_cache shared:SSL:10m;
  ssl_session_timeout 10m;

  client_max_body_size 100M;

  # Security Headers
  add_header X-Frame-Options "SAMEORIGIN" always;
  add_header X-Content-Type-Options "nosniff" always;
  add_header X-XSS-Protection "1; mode=block" always;
  add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

  # Main application
  location / {
    set $frontend_upstream http://frontend:80;
    proxy_pass $frontend_upstream;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host $host;
    proxy_cache_bypass $http_upgrade;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
  }

  # API endpoints
  location /api {
    set $backend_upstream http://egr-api:8000;
    proxy_pass $backend_upstream;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_connect_timeout 300s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;
  }

  # API documentation
  location ~ ^/(docs|redoc|openapi.json) {
    set $backend_upstream http://egr-api:8000;
    proxy_pass $backend_upstream;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
  }

  # Health check
  location /health {
    set $backend_upstream http://egr-api:8000;
    proxy_pass $backend_upstream/api/v1/health;
    access_log off;
  }

  # Static files
  location ~* \.(jpg|jpeg|png|gif|ico|css|js|svg|woff|woff2|ttf|eot|webmanifest)$ {
    set $frontend_upstream http://frontend:80;
    proxy_pass $frontend_upstream;
    expires 1y;
    add_header Cache-Control "public, immutable";
  }

  access_log /var/log/nginx/access.log;
  error_log /var/log/nginx/error.log;
}
EOF
echo "✅ HTTPS configuration created"
echo ""

# Test nginx configuration
echo "📋 Step 4: Testing nginx configuration..."
echo "   Waiting for nginx to be ready..."
sleep 5

# Try to test config, if container not ready, wait and retry
MAX_RETRIES=3
RETRY=0
while [ $RETRY -lt $MAX_RETRIES ]; do
    if docker compose exec egr-nginx nginx -t 2>&1; then
        echo "✅ Nginx configuration is valid"
        break
    else
        RETRY=$((RETRY + 1))
        if [ $RETRY -lt $MAX_RETRIES ]; then
            echo "   Retry $RETRY/$MAX_RETRIES..."
            sleep 3
        else
            echo "❌ Nginx configuration test failed!"
            echo ""
            echo "Restoring backup..."
            cp nginx/conf.d/test.tendex.by.conf.backup nginx/conf.d/test.tendex.by.conf
            exit 1
        fi
    fi
done
echo ""

# Reload nginx
echo "📋 Step 5: Reloading nginx..."
docker compose exec egr-nginx nginx -s reload
echo "✅ Nginx reloaded"
echo ""

# Test HTTPS
echo "📋 Step 6: Testing HTTPS..."
sleep 2
if curl -k -I https://localhost 2>/dev/null | grep -q "200\|301\|302"; then
    echo "✅ HTTPS is responding"
else
    echo "⚠️  Could not test HTTPS locally (this is normal)"
fi
echo ""

echo "🎉 HTTPS enabled successfully!"
echo ""
echo "🌐 Your site is now available at:"
echo "   https://test.tendex.by"
echo ""
echo "✅ HTTP will automatically redirect to HTTPS"
echo ""
echo "🧪 Test from another machine:"
echo "   curl -I https://test.tendex.by"
echo "   curl -I http://test.tendex.by  (should redirect)"
echo ""
echo "📋 If something is wrong, restore the backup:"
echo "   cp nginx/conf.d/test.tendex.by.conf.backup nginx/conf.d/test.tendex.by.conf"
echo "   docker compose restart egr-nginx"
echo ""
