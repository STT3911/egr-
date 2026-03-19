"""Public API token verification"""
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)

async def verify_public_token(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
):
    """Verify Bearer token for public API"""
    if not credentials or credentials.credentials != settings.PUBLIC_API_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Неверный или отсутствующий токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials