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
    REDIS_SOCKET_TIMEOUT_SECONDS: float = 0.5
    REDIS_CONNECT_TIMEOUT_SECONDS: float = 0.5

    # Elasticsearch
    ELASTICSEARCH_ENABLED: bool = False
    ELASTICSEARCH_URL: str = "http://elasticsearch:9200"
    ELASTICSEARCH_INDEX: str = "egr_companies"
    ELASTICSEARCH_REQUEST_TIMEOUT_SECONDS: float = 2.0
    ELASTICSEARCH_REQUIRE_SYNCED: bool = True
    ELASTICSEARCH_REINDEX_BATCH_SIZE: int = 1000
    ELASTICSEARCH_QUEUE_BATCH_SIZE: int = 500
    ELASTICSEARCH_QUEUE_MAX_ATTEMPTS: int = 10
    ELASTICSEARCH_QUEUE_SCHEDULE_SECONDS: int = 30

    # Celery
    CELERY_BROKER_URL: str = "redis://redis:6379/4"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/5"

    # EGR API (все запросы через HTTPS для безопасности и скорости)
    EGR_API_URL: str = "https://egr.gov.by/api/v2/egr"
    EGR_MOBILE_API_URL: str = "https://egr.gov.by/egrmobile/api/v1"
    GIAS_DIRECTORY_API_URL: str = "https://gias.by/directory/api/v1"
    GIAS_DIRECTORY_TIMEOUT_SECONDS: float = 30.0
    GIAS_DIRECTORY_PAGE_SIZE: int = 200

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
    PUBLIC_API_TOKEN: str = "changeme-public-token"
    ALLOWED_API_KEYS: str = ""  # Comma-separated list of API keys
    
    # Security - Rate Limiting (requests per minute)
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_LOOKUP_PER_MINUTE: Optional[int] = 20  # Stricter for lookup/search (anti-parser)

    # Nalog debt (portal.nalog.gov.by) — папка для выгрузки JSON
    NALOG_DEBT_OUT_DIR: str = "dolg_data"

    # Экспорт БД в JSON (путь относительно корня проекта; в контейнере = /app/...)
    DB_EXPORT_DIR: str = "data/db_export"

    # GRP: включать ли задачи grp_fetch_raw / grp_process_raw в расписание Beat (по умолчанию выключено — запуск вручную)
    GRP_SCHEDULE_ENABLED: bool = False
    GRP_FETCH_LIMIT: int = 60
    GRP_FETCH_BATCH_SIZE: int = 10
    GRP_FETCH_CONCURRENCY: int = 2
    GRP_FETCH_MAX_RETRIES: int = 4
    GRP_FETCH_SUCCESS_DELAY_SECONDS: float = 2.0
    GRP_FETCH_RETRY_BASE_DELAY_SECONDS: float = 5.0
    GRP_FETCH_RETRY_COOLDOWN_MINUTES: int = 30
    GRP_FETCH_SCHEDULE_SECONDS: int = 300
    GRP_PROCESS_LIMIT: int = 500
    GRP_PROCESS_SCHEDULE_SECONDS: int = 60

    # GIAS Directory: ежедневная синхронизация реестров
    GIAS_SYNC_ENABLED: bool = True

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost:5174,http://localhost:8000,http://localhost:8080,http://test.tendex.by,https://test.tendex.by"
    
    # Bitrix24 Integration
    BITRIX_CLIENT_ID: Optional[str] = None
    BITRIX_CLIENT_SECRET: Optional[str] = None
    
    # External service integration
    APP_URL: Optional[str] = None
    SECRET_KEY: Optional[str] = None
    TENDEX_API_URL: Optional[str] = None
    TENDEX_API_KEY: Optional[str] = None
    
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
        "case_sensitive": False,
        "extra": "ignore"  # Allow additional env vars without causing errors
    }


# Create single instance of settings
settings = Settings()
