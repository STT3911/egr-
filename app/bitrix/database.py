"""
Async database configuration for Bitrix24 integration.
Uses separate async engine from main sync database.
"""

import asyncio
import sys

# Fix for Windows + psycopg async mode
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.core.config import settings

# Create async engine for Bitrix24
BITRIX_DATABASE_URL = settings.DATABASE_URL.replace(
    "postgresql://", "postgresql+asyncpg://"
).split("?")[0]  # Strip query params like client_encoding

# ИСПРАВЛЕНИЕ 1: Настройка пула соединений для работы с вебхуками
async_engine = create_async_engine(
    BITRIX_DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,      # Проверять живо ли соединение перед использованием
    pool_size=20,            # Держать 20 постоянных соединений в пуле
    max_overflow=10,         # Разрешить еще 10 временных сверх лимита (при пиковых нагрузках)
    pool_timeout=30,         # Ждать 30 секунд, если все соединения заняты, прежде чем выдать ошибку
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_db():
    """Async database session dependency."""
    # ИСПРАВЛЕНИЕ 2: async with сам корректно закроет сессию. 
    # try/finally здесь не нужен.
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Initialize database tables."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)