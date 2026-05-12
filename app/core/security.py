"""Security utilities for API authentication and rate limiting."""
from fastapi import HTTPException, Security, Request
from fastapi.security import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN, HTTP_429_TOO_MANY_REQUESTS
from app.core.config import settings
from app.core.logger import get_logger
from collections import defaultdict
from datetime import datetime, timedelta
import hmac
import threading

logger = get_logger("security")

# API Key authentication
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_allowed_api_keys() -> set:
    """Parse and return allowed API keys from config."""
    if not settings.ALLOWED_API_KEYS:
        return set()
    return {key.strip() for key in settings.ALLOWED_API_KEYS.split(",") if key.strip()}


def _is_public_api_route(request: Request) -> bool:
    """Allow only intentionally public read endpoints without an API key."""
    path = request.url.path
    method = request.method.upper()
    force_refresh = (request.query_params.get("force_refresh") or "").lower()

    if method != "GET":
        return False

    if force_refresh in {"1", "true", "yes", "on"}:
        return False

    if path == "/api/v1/companies/lookup":
        return True

    company_prefix = "/api/v1/companies/"
    if path.startswith(company_prefix):
        suffix = path[len(company_prefix):].strip("/")
        return bool(suffix.isdigit() and len(suffix) == 9)

    grp_prefix = "/api/v1/grp/"
    if path.startswith(grp_prefix):
        suffix = path[len(grp_prefix):].strip("/")
        return bool(suffix.isdigit() and len(suffix) == 9)

    return False


async def verify_api_key(request: Request, api_key: str = Security(api_key_header)) -> str:
    """
    Verify API key from header.
    Returns the API key if valid, raises HTTPException otherwise.
    """
    path = request.url.path
    
    if _is_public_api_route(request):
        return "public-access"

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
    
    if not any(hmac.compare_digest(api_key, allowed_key) for allowed_key in allowed_keys):
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


def _get_client_ip(request: Request) -> str:
    """Real client IP when behind Nginx/reverse proxy (X-Real-IP, then X-Forwarded-For)."""
    real = request.headers.get("X-Real-IP")
    if real:
        return real.strip().split(",")[0].strip()
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.strip().split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


async def rate_limit_check(request: Request):
    """
    Rate limit by real client IP (or API key). Stricter limit for search/lookup to slow down parsers.
    """
    if not settings.RATE_LIMIT_ENABLED:
        return

    client_ip = _get_client_ip(request)
    api_key = request.headers.get("X-API-Key", "")
    client_id = f"key:{api_key[:20]}" if api_key else f"ip:{client_ip}"

    # Stricter limit for search/lookup (часто бьют парсеры)
    path = request.url.path or ""
    is_lookup = "/lookup" in path or "/companies/" in path and "raw" not in path
    max_requests = (
        getattr(settings, "RATE_LIMIT_LOOKUP_PER_MINUTE", None) or settings.RATE_LIMIT_PER_MINUTE
    )
    if is_lookup and hasattr(settings, "RATE_LIMIT_LOOKUP_PER_MINUTE") and settings.RATE_LIMIT_LOOKUP_PER_MINUTE is not None:
        max_requests = settings.RATE_LIMIT_LOOKUP_PER_MINUTE

    allowed = rate_limiter.is_allowed(
        client_id=client_id,
        max_requests=max_requests,
        window_seconds=60,
    )

    if not allowed:
        logger.warning(f"Rate limit exceeded for {client_id} path={path}")
        raise HTTPException(
            status_code=HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {max_requests} requests per minute.",
        )
