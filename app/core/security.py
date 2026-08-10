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
        if suffix.isdigit() and len(suffix) == 9:
            return True
        if suffix.endswith("/tax-debt"):
            unp = suffix.removesuffix("/tax-debt").strip("/")
            return bool(unp.isdigit() and len(unp) == 9)
        if suffix.endswith("/geocode"):
            unp = suffix.removesuffix("/geocode").strip("/")
            return bool(unp.isdigit() and len(unp) == 9)
        if suffix.endswith("/related"):
            unp = suffix.removesuffix("/related").strip("/")
            return bool(unp.isdigit() and len(unp) == 9)
        if suffix.endswith("/risk"):
            unp = suffix.removesuffix("/risk").strip("/")
            return bool(unp.isdigit() and len(unp) == 9)

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
    """Thread-safe in-memory request and unique-item rate limiter."""
    
    def __init__(self):
        self.requests = defaultdict(list)
        self.unique_items = defaultdict(dict)
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

    def is_unique_item_allowed(
        self,
        client_id: str,
        item_id: str,
        max_items: int,
        window_seconds: int = 60,
    ) -> bool:
        """Allow repeated requests for an item but cap distinct items per window."""
        now = datetime.now()
        cutoff = now - timedelta(seconds=window_seconds)

        with self.lock:
            active_items = {
                key: first_seen
                for key, first_seen in self.unique_items[client_id].items()
                if first_seen > cutoff
            }
            self.unique_items[client_id] = active_items

            # A company dossier loads several endpoints. They all belong to the
            # same user-visible lookup and must not consume the quota again.
            if item_id in active_items:
                return True

            if len(active_items) >= max_items:
                return False

            active_items[item_id] = now
            return True
    
    def cleanup_old_entries(self):
        """Remove entries older than 5 minutes to prevent memory leaks."""
        cutoff = datetime.now() - timedelta(minutes=5)
        with self.lock:
            self.requests = defaultdict(
                list,
                {k: v for k, v in self.requests.items() if any(t > cutoff for t in v)}
            )
            self.unique_items = defaultdict(
                dict,
                {
                    client_id: {
                        item_id: first_seen
                        for item_id, first_seen in items.items()
                        if first_seen > cutoff
                    }
                    for client_id, items in self.unique_items.items()
                    if any(first_seen > cutoff for first_seen in items.values())
                },
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


def _get_company_unp(request: Request) -> str | None:
    """Return the company UNP represented by a public dossier request."""
    path_parts = [part for part in request.url.path.split("/") if part]

    # /api/v1/companies/{unp} and all dossier sub-resources.
    if len(path_parts) >= 4 and path_parts[:3] == ["api", "v1", "companies"]:
        candidate = path_parts[3]
        if candidate.isdigit() and len(candidate) == 9:
            return candidate

    # The company page also loads its cached GRP block separately.
    if len(path_parts) == 4 and path_parts[:3] == ["api", "v1", "grp"]:
        candidate = path_parts[3]
        if candidate.isdigit() and len(candidate) == 9:
            return candidate

    return None


async def rate_limit_check(request: Request):
    """
    Rate limit by real client IP (or API key).

    General traffic and lookup/search use independent request buckets. Company
    dossier endpoints additionally share a quota by distinct UNP, so the 5-6
    HTTP requests made by one page view count as one company lookup.
    """
    if not settings.RATE_LIMIT_ENABLED:
        return

    client_ip = _get_client_ip(request)
    api_key = request.headers.get("X-API-Key", "")
    client_id = f"key:{api_key[:20]}" if api_key else f"ip:{client_ip}"

    path = request.url.path or ""

    allowed = rate_limiter.is_allowed(
        client_id=f"general:{client_id}",
        max_requests=settings.RATE_LIMIT_PER_MINUTE,
        window_seconds=60,
    )

    if not allowed:
        logger.warning(f"Rate limit exceeded for {client_id} path={path}")
        raise HTTPException(
            status_code=HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Rate limit exceeded. Maximum "
                f"{settings.RATE_LIMIT_PER_MINUTE} requests per minute."
            ),
            headers={"Retry-After": "60"},
        )

    if path == "/api/v1/companies/lookup":
        lookup_limit = (
            settings.RATE_LIMIT_LOOKUP_PER_MINUTE
            if settings.RATE_LIMIT_LOOKUP_PER_MINUTE is not None
            else settings.RATE_LIMIT_PER_MINUTE
        )
        if not rate_limiter.is_allowed(
            client_id=f"lookup:{client_id}",
            max_requests=lookup_limit,
            window_seconds=60,
        ):
            logger.warning(f"Lookup rate limit exceeded for {client_id}")
            raise HTTPException(
                status_code=HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "Lookup rate limit exceeded. Maximum "
                    f"{lookup_limit} searches per minute."
                ),
                headers={"Retry-After": "60"},
            )

    company_unp = _get_company_unp(request)
    if company_unp and not rate_limiter.is_unique_item_allowed(
        client_id=f"company:{client_id}",
        item_id=company_unp,
        max_items=settings.RATE_LIMIT_COMPANIES_PER_MINUTE,
        window_seconds=60,
    ):
        logger.warning(
            f"Company rate limit exceeded for {client_id} unp={company_unp} path={path}"
        )
        raise HTTPException(
            status_code=HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Company lookup rate limit exceeded. Maximum "
                f"{settings.RATE_LIMIT_COMPANIES_PER_MINUTE} companies per minute."
            ),
            headers={"Retry-After": "60"},
        )
