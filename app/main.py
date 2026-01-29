"""Main FastAPI application"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.api.v1.endpoints import companies, references, grp
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

# CORS middleware with security improvements
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Explicit methods
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],  # Explicit headers
    max_age=3600,  # Cache preflight requests for 1 hour
)

# Rate limiting middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting to all requests."""
    from app.core.security import rate_limit_check
    
    # Skip rate limiting for health checks
    if request.url.path in ["/api/v1/health", "/api/v1/health/ready"]:
        return await call_next(request)
    
    # Check rate limit
    await rate_limit_check(request)
    
    response = await call_next(request)
    return response

# Include routers
app.include_router(companies.router, prefix="/api/v1/companies", tags=["Companies"])
app.include_router(references.router, prefix="/api/v1/references", tags=["References"])
app.include_router(grp.router, prefix="/api/v1/grp", tags=["GRP"])


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
    return {
        "message": "EGR Aggregator API",
        "docs": "/docs",
        "health": "/api/v1/health"
    }




