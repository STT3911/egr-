"""
Application configuration settings for EGR Aggregator.

This module loads and validates configuration from environment variables
using Pydantic Settings.
"""

from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator
from typing import List, Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: Optional[str] = None
    DB_HOST: str = "db"
    DB_PORT: int = 5432
    DB_NAME: str = "egr_db"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""

    # Redis
    REDIS_URL: str = "redis://redis:6379"
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379

    # Celery
    CELERY_BROKER_URL: str = "redis://redis:6379/4"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/5"

    # EGR API (все запросы через HTTPS для безопасности и скорости)
    EGR_API_URL: str = "https://egr.gov.by/api/v2/egr"
    EGR_MOBILE_API_URL: str = "https://egr.gov.by/egrmobile/api/v1"

    # Application
    APP_ENV: str = "production"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Database connection pool settings
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_RECYCLE: int = 3600

    # Security - API Authentication
    API_KEY: Optional[str] = None
    ALLOWED_API_KEYS: str = ""  # Comma-separated list of API keys
    
    # Security - Rate Limiting (requests per minute)
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost:5174,http://localhost:8000,http://localhost:8080,http://test.tendex.by,https://test.tendex.by"
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS_ORIGINS string into list."""
        if isinstance(self.CORS_ORIGINS, str):
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        return self.CORS_ORIGINS

    @field_validator('DATABASE_URL')
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate database URL format."""
        if not v:
            return v
        if v == "postgresql://user:password@localhost/dbname":
            raise ValueError(
                'DATABASE_URL must be set to a valid database connection string'
            )
        return v

    @model_validator(mode="after")
    def ensure_database_url(self):
        """Build DATABASE_URL from parts if not provided."""
        if not self.DATABASE_URL:
            user = self.DB_USER
            pwd = self.DB_PASSWORD
            host = self.DB_HOST
            port = self.DB_PORT
            name = self.DB_NAME
            auth_part = f"{user}:{pwd}@" if pwd else f"{user}@"
            self.DATABASE_URL = f"postgresql://{auth_part}{host}:{port}/{name}"
        return self

    @field_validator('APP_ENV')
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        """Validate APP_ENV value."""
        allowed = ['development', 'production', 'testing']
        if v not in allowed:
            raise ValueError(f'APP_ENV must be one of: {", ".join(allowed)}')
        return v

    @field_validator('LOG_LEVEL')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate LOG_LEVEL value."""
        allowed = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in allowed:
            raise ValueError(f'LOG_LEVEL must be one of: {", ".join(allowed)}')
        return v.upper()

    model_config = {
        "env_file": ".env",
        "case_sensitive": False
    }


# Create single instance of settings
settings = Settings()