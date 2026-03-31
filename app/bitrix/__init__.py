"""Bitrix24 integration module."""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from app.bitrix.bitrix_client import BitrixClient, BitrixAPIError
from app.bitrix.database import get_db

logger = logging.getLogger(__name__)

# Security scheme for Bitrix auth
security_scheme = APIKeyHeader(name="X-Bitrix-Token", auto_error=False)


async def get_bitrix_client(
    db: AsyncSession = Depends(get_db),
) -> BitrixClient:
    """Get BitrixClient instance."""
    return BitrixClient(db)


async def is_admin_required(
    bitrix: BitrixClient = Depends(get_bitrix_client),
) -> bool:
    """
    Dependency that checks if current user has admin rights.
    
    Raises:
        HTTPException: 403 if user is not admin
        
    Returns:
        True if user is admin
    """
    try:
        is_admin = await bitrix.is_admin()
        if not is_admin:
            logger.warning("Access denied: user is not admin")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Доступ запрещен. Требуются права администратора.",
            )
        return True
    except BitrixAPIError as e:
        logger.error(f"Error checking admin status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка проверки прав администратора: {e}",
        )


async def get_current_user_info(
    bitrix: BitrixClient = Depends(get_bitrix_client),
) -> dict:
    """
    Dependency that returns current user info.
    
    Raises:
        HTTPException: 401 if user not authenticated
        
    Returns:
        User info dict from Bitrix24
    """
    user_info = await bitrix.get_current_user()
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не удалось получить информацию о пользователе",
        )
    return user_info


# Type aliases for dependency injection
BitrixClientDep = Annotated[BitrixClient, Depends(get_bitrix_client)]
AdminRequired = Annotated[bool, Depends(is_admin_required)]
CurrentUser = Annotated[dict, Depends(get_current_user_info)]
