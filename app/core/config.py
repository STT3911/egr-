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
    # Таймаут ES-запросов. 2с было слишком жёстко — тяжёлый _search не успевал и
    # клиент его убивал, поиск падал на медленный Postgres. 5с — страховка; сам
    # запрос после упрощения должен укладываться в сотни мс.
    ELASTICSEARCH_REQUEST_TIMEOUT_SECONDS: float = 5.0
    # Fuzzy-поиск (толерантность к опечаткам). Дорого и нестабильно поверх edge-ngram
    # полей (fuzzy по огромному словарю ngram-термов). По умолчанию выключен ради
    # скорости — edge-ngram и так ловит префикс/частичный ввод. Включить при нужде.
    ELASTICSEARCH_FUZZY_SEARCH: bool = False
    ELASTICSEARCH_REQUIRE_SYNCED: bool = True
    # Сколько непроиндексированных записей в очереди допустимо, прежде чем lookup
    # перестаёт использовать ES (мягкий гейт). Лёгкая рассинхронизация индекса для
    # поиска допустима — несколько pending-записей не должны ронять поиск на медленный
    # Postgres LIKE. 0 = старое строгое поведение (любой pending → ES пропускается).
    ELASTICSEARCH_SYNC_MAX_OUTSTANDING: int = 5000
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
    PUBLIC_API_TOKEN: Optional[str] = None
    # Отдельный токен ТОЛЬКО для замороженного внешнего эндпоинта /api/v1/stable/* .
    # Нигде больше не используется (по требованию прод-интеграции tenders.by).
    STABLE_API_TOKEN: Optional[str] = None
    ALLOWED_API_KEYS: str = ""  # Comma-separated list of API keys
    ALLOWED_HOSTS: str = "test.tendex.by,localhost,127.0.0.1,egr-api,egr_api"

    # Admin panel authentication
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: Optional[str] = None
    ADMIN_PASSWORD_HASH: Optional[str] = None
    ADMIN_SESSION_TTL_HOURS: int = 12
    ADMIN_COOKIE_SECURE: Optional[bool] = None
    
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

    # PVT/HTP residents sync from park.by. Disabled by default; enable when Celery Beat should run it.
    PVT_SCHEDULE_ENABLED: bool = False
    PVT_SYNC_LIMIT: Optional[int] = 500
    PVT_SYNC_BATCH_SIZE: int = 100
    PVT_SYNC_DELAY_SECONDS: float = 0.2
    PVT_SYNC_TIMEOUT_SECONDS: float = 30.0
    PVT_SYNC_ONLY_MISSING: bool = True
    PVT_SYNC_SCHEDULE_SECONDS: int = 86400

    # GIAS Directory: ежедневная синхронизация реестров
    GIAS_SYNC_ENABLED: bool = True

    # Подписки: периодический ПРЯМОЙ перезабор отслеживаемых компаний.
    # Обходит лимит дневного фида (getEventByPeriod ~2500/день без пагинации) —
    # гарантирует, что изменения по подписанным компаниям не теряются.
    REFRESH_SUBSCRIBED_SCHEDULE_SECONDS: int = 21600   # каждые 6 часов
    REFRESH_SUBSCRIBED_BATCH_SIZE: int = 30

    # Полнота базы: сверка по состояниям (getRegNumByState) — находит новые компании
    # и сменившие статус по ВСЕЙ базе, минуя кап дневного фида 2500.
    EGR_RECONCILE_SCHEDULE_SECONDS: int = 86400        # раз в сутки
    EGR_RECONCILE_LIMIT: int = 20000                   # сколько (пере)заборов ставить за прогон

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost:5174,http://localhost:8000,http://localhost:8080,http://test.tendex.by,https://test.tendex.by"
    
    # Bitrix24 Integration
    BITRIX_CLIENT_ID: Optional[str] = None
    BITRIX_CLIENT_SECRET: Optional[str] = None
    # Keep-alive: принудительный refresh токена по расписанию, чтобы refresh_token
    # не протух при простое (живёт ~30 дней, обновляется при каждом обращении).
    BITRIX_KEEPALIVE_ENABLED: bool = True
    BITRIX_KEEPALIVE_SCHEDULE_SECONDS: int = 86400   # раз в сутки
    # Алерты об сбоях фоновых задач (опционально; если не задано — только лог).
    ALERT_TELEGRAM_BOT_TOKEN: Optional[str] = None
    ALERT_TELEGRAM_CHAT_ID: Optional[str] = None
    
    # External service integration
    APP_URL: Optional[str] = None
    SECRET_KEY: Optional[str] = None
    TENDEX_API_URL: Optional[str] = None
    TENDEX_API_KEY: Optional[str] = None

    # Bankrot.gov.by — синхронизация дел о банкротстве
    BANKROT_API_URL: str = "https://api.bankrot.gov.by/v1"
    BANKROT_API_TOKEN: Optional[str] = None          # Bearer token (обязателен для работы API)
    BANKROT_PAGE_SIZE: int = 100                      # кол-во кейсов на страницу
    BANKROT_PAGE_DELAY_SECONDS: float = 0.5          # пауза между страницами
    BANKROT_DETAIL_DELAY_SECONDS: float = 0.2        # пауза между detail/judgements запросами
    BANKROT_MAX_RETRIES: int = 3                      # попыток при ошибке
    BANKROT_RETRY_DELAY_SECONDS: float = 2.0         # базовая задержка между попытками
    BANKROT_TIMEOUT_SECONDS: float = 30.0            # таймаут HTTP запроса
    BANKROT_OUTPUT_DIR: str = "data/bankrot"         # куда сохранять JSON-выгрузку
    BANKROT_SAVE_EVERY: int = 50                     # промежуточный flush каждые N кейсов
    BANKROT_SCHEDULE_ENABLED: bool = False           # включить периодическую задачу
    BANKROT_SCHEDULE_SECONDS: int = 86400            # интервал периодической задачи (сек)

    # license.gov.by license registry synchronization
    LICENSE_API_URL: str = "https://license.gov.by/api/licenses"
    LICENSE_PAGE_SIZE: int = 200
    LICENSE_TIMEOUT_SECONDS: float = 30.0
    LICENSE_PAGE_DELAY_SECONDS: float = 0.2
    LICENSE_SAVE_EVERY: int = 500
    LICENSE_VERIFY_TLS: bool = True
    LICENSE_SCHEDULE_ENABLED: bool = False
    LICENSE_SCHEDULE_SECONDS: int = 86400

    # Геокодинг адресов через OSM/Nominatim (координаты можно хранить, в отличие
    # от Яндекса). Nominatim требует валидный User-Agent с контактом и лимит 1 req/sec.
    NOMINATIM_BASE_URL: str = "https://nominatim.openstreetmap.org"
    NOMINATIM_USER_AGENT: str = "egr-service/1.0 (+https://test.tendex.by; stt04032@gmail.com)"
    NOMINATIM_TIMEOUT_SECONDS: float = 30.0
    NOMINATIM_DELAY_SECONDS: float = 1.1     # пауза между запросами (лимит 1/сек)
    NOMINATIM_COUNTRY_CODES: str = "by"      # ограничиваем поиск Беларусью
    GEOCODE_BATCH_SIZE: int = 40             # адресов за один прогон задачи
    GEOCODE_RETRY_AFTER_DAYS: int = 7        # через сколько дней повторять неудавшийся геокод
    GEOCODE_SCHEDULE_ENABLED: bool = False   # включить периодический геокодинг в Beat
    GEOCODE_SCHEDULE_SECONDS: int = 3600

    # Яндекс HTTP-геокодер (точное покрытие по РБ; OSM для РБ адресов непригоден).
    # Ключ «API Геокодера» (тот же формат, что geocode-maps.yandex.ru/1.x в Postman).
    YANDEX_GEOCODER_URL: str = "https://geocode-maps.yandex.ru/1.x/"
    YANDEX_GEOCODER_API_KEY: Optional[str] = None
    YANDEX_GEOCODER_TIMEOUT_SECONDS: float = 15.0

    # Telegram bot
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_API_BASE_URL: str = "http://egr-api:8000"
    TELEGRAM_API_KEY: Optional[str] = None
    TELEGRAM_LOOKUP_LIMIT: int = 5
    TELEGRAM_HTTP_TIMEOUT_SECONDS: float = 10.0
    TELEGRAM_POLL_TIMEOUT_SECONDS: int = 30
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS_ORIGINS string into list."""
        if isinstance(self.CORS_ORIGINS, str):
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        return self.CORS_ORIGINS

    @property
    def allowed_hosts_list(self) -> List[str]:
        """Parse ALLOWED_HOSTS string into list."""
        if isinstance(self.ALLOWED_HOSTS, str):
            return [host.strip() for host in self.ALLOWED_HOSTS.split(",") if host.strip()]
        return self.ALLOWED_HOSTS

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
