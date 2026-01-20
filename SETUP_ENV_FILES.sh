#!/bin/bash
set -e

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

if [ ! -f "frontend/.env" ] && [ -f "frontend/.env.example" ]; then
  cp frontend/.env.example frontend/.env
  echo "Created frontend/.env from frontend/.env.example"
fi
#!/bin/bash
# Script to create necessary .env files for the project

echo "🔧 Creating environment files..."

# Create frontend/.env.development
cat > frontend/.env.development << EOF
# Development environment
VITE_API_URL=http://localhost:8002
EOF
echo "✅ Created frontend/.env.development"

# Create frontend/.env.production
cat > frontend/.env.production << EOF
# Production environment
# Update this URL to your production domain
VITE_API_URL=http://localhost/api
EOF
echo "✅ Created frontend/.env.production"

# Check if frontend/.env exists, if not create it
if [ ! -f "frontend/.env" ]; then
    cat > frontend/.env << EOF
# API Configuration for local development (without Docker)
VITE_API_URL=http://localhost:8000
EOF
    echo "✅ Created frontend/.env"
else
    echo "ℹ️  frontend/.env already exists, skipping..."
fi

echo ""
echo "✨ All environment files created!"
echo ""
echo "📝 Next steps:"
echo "   1. Review and update URLs if needed"
echo "   2. Run: docker-compose --profile dev up -d"
echo "   3. Open: http://localhost:5173"
echo ""
