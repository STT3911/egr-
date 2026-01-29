"""Main FastAPI application"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.endpoints import companies, references, grp
from app.core.config import settings
from app.core.logger import logger

# Create FastAPI app
app = FastAPI(
    title="EGR Aggregator API",
    description="Микросервис для агрегации данных из API ЕГР Республики Беларусь",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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




