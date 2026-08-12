#!/bin/bash
# Quick status check for company.tenders.by Docker services

echo "📊 Status check for company.tenders.by"
echo "==================================="

# Service status
echo ""
echo "🐳 Docker services:"
docker compose ps

# Health checks
echo ""
echo "🏥 Health checks:"

# Database
if docker compose exec -T db pg_isready -U postgres > /dev/null 2>&1; then
    echo "✅ PostgreSQL: Healthy"
else
    echo "❌ PostgreSQL: Unhealthy"
fi

# Redis
if docker compose exec -T redis redis-cli ping | grep -q PONG; then
    echo "✅ Redis: Healthy"
else
    echo "❌ Redis: Unhealthy"
fi

# API
if curl -f --max-time 5 http://localhost:8002/api/v1/health > /dev/null 2>&1; then
    echo "✅ API: Responding"
else
    echo "❌ API: Not responding"
fi

# Frontend
if curl -f --max-time 5 http://localhost:3000 > /dev/null 2>&1; then
    echo "✅ Frontend: Responding"
else
    echo "❌ Frontend: Not responding"
fi

# Nginx
if curl -f --max-time 5 http://localhost > /dev/null 2>&1; then
    echo "✅ Nginx: Responding on port 80"
else
    echo "❌ Nginx: Not responding on port 80"
fi

# External access
echo ""
echo "🌐 External access:"
if curl -f --max-time 10 https://company.tenders.by > /dev/null 2>&1; then
    echo "✅ HTTPS: Working"
elif curl -f --max-time 10 http://company.tenders.by > /dev/null 2>&1; then
    echo "⚠️ HTTP: Working (HTTPS not configured)"
else
    echo "❌ External access: Not working (DNS or config issue)"
fi

# Resource usage
echo ""
echo "💾 Resource usage:"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"

echo ""
echo "📋 Logs: docker compose logs [service-name]"
echo "🔄 Restart: docker compose restart [service-name]"
echo "🛑 Stop all: docker compose down"
