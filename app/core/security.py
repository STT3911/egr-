"""Security utilities for API authentication and rate limiting."""
from fastapi import HTTPException, Security, Request
from fastapi.security import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN, HTTP_429_TOO_MANY_REQUESTS
from app.core.config import settings
from app.core.logger import get_logger
from collections import defaultdict
from datetime import datetime, timedelta
import threading

logger = get_logger("security")

# API Key authentication
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_allowed_api_keys() -> set:
    """Parse and return allowed API keys from config."""
    if not settings.ALLOWED_API_KEYS:
        return set()
    return {key.strip() for key in settings.ALLOWED_API_KEYS.split(",") if key.strip()}


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Verify API key from header.
    Returns the API key if valid, raises HTTPException otherwise.
    """
    # Skip auth in development mode if no keys configured
    if settings.APP_ENV == "development" and not settings.ALLOWED_API_KEYS:
        logger.warning("⚠️  API authentication disabled in development mode")
        return "dev-mode"
    
    if not api_key:
        logger.warning("Missing API key in request")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Missing API key. Please provide X-API-Key header."
        )
    
    allowed_keys = get_allowed_api_keys()
    
    if not allowed_keys:
        logger.error("No API keys configured! Set ALLOWED_API_KEYS environment variable.")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="API authentication not configured"
        )
    
    if api_key not in allowed_keys:
        logger.warning(f"Invalid API key attempt: {api_key[:8]}...")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )
    
    return api_key


# Rate limiting
class RateLimiter:
    """Simple in-memory rate limiter."""
    
    def __init__(self):
        self.requests = defaultdict(list)
        self.lock = threading.Lock()
    
    def is_allowed(self, client_id: str, max_requests: int, window_seconds: int = 60) -> bool:
        """
        Check if client is allowed to make a request.
        
        Args:
            client_id: Unique identifier for the client (IP or API key)
            max_requests: Maximum number of requests allowed
            window_seconds: Time window in seconds (default 60)
        
        Returns:
            True if request is allowed, False otherwise
        """
        now = datetime.now()
        cutoff = now - timedelta(seconds=window_seconds)
        
        with self.lock:
            # Clean old requests
            self.requests[client_id] = [
                req_time for req_time in self.requests[client_id]
                if req_time > cutoff
            ]
            
            # Check if limit exceeded
            if len(self.requests[client_id]) >= max_requests:
                return False
            
            # Add current request
            self.requests[client_id].append(now)
            return True
    
    def cleanup_old_entries(self):
        """Remove entries older than 5 minutes to prevent memory leaks."""
        cutoff = datetime.now() - timedelta(minutes=5)
        with self.lock:
            self.requests = defaultdict(
                list,
                {k: v for k, v in self.requests.items() if any(t > cutoff for t in v)}
            )


# Global rate limiter instance
rate_limiter = RateLimiter()


async def rate_limit_check(request: Request):
    """
    Middleware to check rate limits.
    Uses client IP or API key as identifier.
    """
    if not settings.RATE_LIMIT_ENABLED:
        return
    
    # Get client identifier (prefer API key, fallback to IP)
    api_key = request.headers.get("X-API-Key", "")
    client_ip = request.client.host if request.client else "unknown"
    client_id = api_key[:16] if api_key else client_ip
    
    # Check rate limit
    allowed = rate_limiter.is_allowed(
        client_id=client_id,
        max_requests=settings.RATE_LIMIT_PER_MINUTE,
        window_seconds=60
    )
    
    if not allowed:
        logger.warning(f"Rate limit exceeded for {client_id}")
        raise HTTPException(
            status_code=HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {settings.RATE_LIMIT_PER_MINUTE} requests per minute."
        )
