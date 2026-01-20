@echo off
if not exist ".env" (
  if exist ".env.example" (
    copy ".env.example" ".env" >nul
    echo Created .env from .env.example
  )
)

if not exist "frontend\\.env" (
  if exist "frontend\\.env.example" (
    copy "frontend\\.env.example" "frontend\\.env" >nul
    echo Created frontend\\.env from frontend\\.env.example
  )
)
@echo off
REM Script to create necessary .env files for the project (Windows)

echo Creating environment files...

REM Create frontend/.env.development
(
echo # Development environment
echo VITE_API_URL=http://localhost:8002
) > frontend\.env.development
echo Created frontend/.env.development

REM Create frontend/.env.production
(
echo # Production environment
echo # Update this URL to your production domain
echo VITE_API_URL=http://localhost/api
) > frontend\.env.production
echo Created frontend/.env.production

REM Check if frontend/.env exists
if not exist "frontend\.env" (
    (
    echo # API Configuration for local development ^(without Docker^)
    echo VITE_API_URL=http://localhost:8000
    ) > frontend\.env
    echo Created frontend/.env
) else (
    echo frontend/.env already exists, skipping...
)

echo.
echo All environment files created!
echo.
echo Next steps:
echo    1. Review and update URLs if needed
echo    2. Run: docker-compose --profile dev up -d
echo    3. Open: http://localhost:5173
echo.
pause
