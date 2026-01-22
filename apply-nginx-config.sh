#!/bin/bash

# Apply Nginx Configuration for HTTPS
# This script activates HTTPS configuration after SSL certificates are obtained

set -e

echo "🔧 Applying Nginx HTTPS configuration..."

# Check if docker compose is available
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed"
    exit 1
fi

# Check if nginx config exists
if [ ! -f "nginx/conf.d/test.tendex.by.conf" ]; then
    echo "❌ Nginx config not found: nginx/conf.d/test.tendex.by.conf"
    exit 1
fi

# Check if SSL certificates exist
if [ ! -f "ssl/fullchain.pem" ] || [ ! -f "ssl/privkey.pem" ]; then
    echo "⚠️  WARNING: SSL certificates not found in ./ssl/"
    echo "   Make sure certificates are in place before applying config"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Validate nginx config
echo "✅ Validating nginx configuration..."
docker compose exec egr-nginx nginx -t || {
    echo "❌ Nginx config validation failed!"
    exit 1
}

# Reload nginx
echo "🔄 Reloading nginx..."
docker compose exec egr-nginx nginx -s reload

echo ""
echo "✅ Nginx configuration applied successfully!"
echo ""
echo "🌐 Your site should now be available at:"
echo "   - https://test.tendex.by (secure)"
echo "   - http://test.tendex.by (redirects to HTTPS)"
echo ""
echo "🧪 Test the API:"
echo "   curl -I https://test.tendex.by/api/v1/health"
echo ""
echo "🔍 Check logs:"
echo "   docker compose logs -f egr-nginx"
echo ""
