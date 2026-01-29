"""Custom error handlers for FastAPI"""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.config import settings
from app.core.logger import get_logger
import traceback

logger = get_logger("error_handlers")


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors"""
    logger.warning(f"Validation error on {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation error",
            "errors": exc.errors() if settings.DEBUG else "Invalid input data"
        }
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions"""
    logger.warning(f"HTTP {exc.status_code} on {request.url.path}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Handle all uncaught exceptions"""
    # Log full traceback for debugging
    logger.error(f"Unhandled exception on {request.url.path}: {exc}")
    logger.error(traceback.format_exc())
    
    # In production, hide detailed error messages
    if settings.APP_ENV == "production":
        detail = "Internal server error. Please contact support."
    else:
        detail = f"{type(exc).__name__}: {str(exc)}"
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": detail,
            "type": type(exc).__name__ if settings.DEBUG else None
        }
    )
