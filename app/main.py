"""Main FastAPI application"""
from app.bitrix.admin import router as bitrix_admin_router
from app.bitrix.install import router as bitrix_install_router
from app.bitrix.webhook import router as bitrix_webhook_router
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.api.v1.endpoints import companies, references, grp, gias
from app.core.config import settings
from app.core.logger import logger
from app.core.error_handlers import (
    validation_exception_handler,
    http_exception_handler,
    general_exception_handler
)

# Create FastAPI app with conditional docs
app = FastAPI(
    title="EGR Aggregator API",
    description="Микросервис для агрегации данных из API ЕГР Республики Беларусь",
    version="1.0.0",
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/redoc" if settings.APP_ENV != "production" else None,
    openapi_url="/openapi.json" if settings.APP_ENV != "production" else None,
)

# Register error handlers
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts_list,
)

# CORS middleware with security improvements
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Explicit methods
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],  # Explicit headers
    max_age=3600,  # Cache preflight requests for 1 hour
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add baseline browser/security headers to every response."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


# Rate limiting middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting to all requests."""
    from app.core.security import rate_limit_check
    
    # Skip rate limiting for health checks
    if request.url.path in ["/api/v1/health", "/api/v1/health/ready"]:
        return await call_next(request)
    
    # Check rate limit. Exceptions raised inside middleware bypass FastAPI's
    # normal exception handlers, so return the response here.
    try:
        await rate_limit_check(request)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )
    
    response = await call_next(request)
    return response

# Include routers
app.include_router(companies.router, prefix="/api/v1/companies", tags=["Companies"])
app.include_router(references.router, prefix="/api/v1/references", tags=["References"])
app.include_router(grp.router, prefix="/api/v1/grp", tags=["GRP"])
app.include_router(gias.router, prefix="/api/v1/gias", tags=["GIAS"])

# Умный поиск интегрирован в companies.router (/api/v1/companies/lookup)

#bitrix

app.include_router(bitrix_admin_router, prefix="/bitrix/admin", tags=["Bitrix24 Admin"])
app.include_router(bitrix_install_router, prefix="/bitrix", tags=["Bitrix24 Install"])
app.include_router(bitrix_webhook_router, prefix="/bitrix/webhook", tags=["Bitrix24 Webhook"])


@app.on_event("startup")
async def startup():
    """Startup event"""
    logger.info("🚀 Starting EGR Aggregator API")
    logger.info(f"Environment: {settings.APP_ENV}")
    logger.info(f"Debug mode: {settings.DEBUG}")


@app.on_event("shutdown")
async def shutdown():
    """Shutdown event"""
    logger.info("👋 Shutting down EGR Aggregator API")


@app.get("/api/v1/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "egr-aggregator",
        "version": "1.0.0"
    }


@app.get("/api/v1/health/ready")
async def health_ready():
    """Readiness check endpoint"""
    # TODO: Add database connectivity check
    return {
        "status": "ready",
        "database": "ok"
    }


@app.get("/")
async def root():
    """Root endpoint"""
    payload = {
        "message": "EGR Aggregator API",
        "health": "/api/v1/health"
    }
    if settings.APP_ENV != "production":
        payload["docs"] = "/docs"
    return payload

