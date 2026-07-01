"""Celery application configuration"""
from celery import Celery
from celery.schedules import crontab
from datetime import timedelta
from app.core.config import settings

celery_app = Celery(
    "egr_aggregator",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.sync_tasks",
        "app.tasks.trade_registry_tasks",
        "app.tasks.park_tasks",
        "app.tasks.bankrot_tasks",
        "app.tasks.license_tasks",
        "app.tasks.webhook_tasks",
        "app.tasks.bitrix_tasks",
        "app.tasks.contacts_tasks",
        "app.tasks.eaeu_sez_tasks",
        "app.tasks.address_tasks",
    ],
)

# Импортируем модуль с задачами для регистрации
from app.tasks import sync_tasks
from app.tasks import trade_registry_tasks
from app.tasks import park_tasks
from app.tasks import bankrot_tasks
from app.tasks import license_tasks
from app.tasks import webhook_tasks
from app.tasks import bitrix_tasks
from app.tasks import contacts_tasks
from app.tasks import eaeu_sez_tasks
from app.tasks import address_tasks

# Базовое расписание: EGR всегда в расписании, GRP — только если GRP_SCHEDULE_ENABLED
_beat_schedule = {
    # ----- EGR: fetch (API → raw) и process (raw → таблицы) -----
    "egr-fetch-raw": {
        "task": "app.tasks.sync_tasks.egr_fetch_raw",
        "schedule": crontab(hour="0,12", minute=30),
        "args": (500,),
        # expires = 12 часов (следующий запуск): стале-задача отбрасывается, не накапливается
        "options": {"expires": 12 * 3600},
    },
    "egr-process-raw": {
        "task": "app.tasks.sync_tasks.egr_process_raw",
        "schedule": crontab(hour="1,13", minute=30),
        "args": (1000,),
        "options": {"expires": 12 * 3600},
    },
    # ----- Остальные задачи (периодические) -----
    "auto-fetch-historical": {
        "task": "app.tasks.sync_tasks.auto_fetch_historical_data",
        "schedule": crontab(day_of_week=0, hour=1, minute=0),
        "args": (1900, 60),
        "options": {"expires": 7 * 24 * 3600},
    },
    "load-from-json": {
        "task": "app.tasks.sync_tasks.load_companies_from_json",
        "schedule": crontab(hour=2, minute=0),
        "args": (True,),
        "options": {"expires": 24 * 3600},
    },
    "sync-daily-changes": {
        "task": "app.tasks.sync_tasks.sync_daily_changes",
        "schedule": crontab(hour=3, minute=0),
        "args": (),
        "options": {"expires": 24 * 3600},
    },
    "update-reference-tables": {
        "task": "app.tasks.sync_tasks.update_reference_tables",
        "schedule": crontab(hour=4, minute=0),
        "args": (),
        "options": {"expires": 24 * 3600},
    },
    "gias-sync-directory-registries": {
        "task": "app.tasks.sync_tasks.sync_gias_directory_registries",
        "schedule": crontab(hour=4, minute=30),
        "args": (),
        "options": {"expires": 24 * 3600},
    },
    "egr-sync-place-locations": {
        "task": "app.tasks.sync_tasks.egr_sync_place_locations",
        "schedule": crontab(hour="2,14", minute=30),
        "args": (500, 20),
        "options": {"expires": 12 * 3600},
    },
    "reprocess-failed-rows": {
        "task": "app.tasks.sync_tasks.reprocess_failed_rows",
        "schedule": crontab(day_of_week=6, hour=5, minute=0),
        "args": (),
        "options": {"expires": 7 * 24 * 3600},
    },
    # Self-healing ретрай ошибочных raw-строк каждые 30 мин (backoff + лимит попыток),
    # чтобы хвост no_data/fetch_failed/parse_failed разгребался сам, без ручных прогонов.
    "retry-failed-rows": {
        "task": "app.tasks.sync_tasks.retry_failed_rows",
        "schedule": crontab(minute="*/30"),
        "args": (300,),
        "options": {"expires": 25 * 60},
    },
    "process-search-index-queue": {
        "task": "app.tasks.sync_tasks.process_search_index_queue",
        "schedule": timedelta(seconds=settings.ELASTICSEARCH_QUEUE_SCHEDULE_SECONDS),
        "args": (settings.ELASTICSEARCH_QUEUE_BATCH_SIZE,),
        # expires = 80% интервала: старые копии отбрасываются, но есть слак под нагрузку
        "options": {"expires": int(settings.ELASTICSEARCH_QUEUE_SCHEDULE_SECONDS * 0.8)},
    },
    # Push-доставка событий подписок на webhook клиента (каждые 60с)
    "deliver-subscription-events": {
        "task": "app.tasks.webhook_tasks.deliver_subscription_events",
        "schedule": timedelta(seconds=60),
        "args": (),
        "options": {"expires": 55},
    },
    # Push-доставка событий подписок в Telegram (каждые 60с)
    "deliver-telegram-events": {
        "task": "app.tasks.webhook_tasks.deliver_telegram_events",
        "schedule": timedelta(seconds=60),
        "args": (),
        "options": {"expires": 55},
    },
    # Прямой перезабор подписанных компаний — надёжная детекция изменений по подпискам
    # в обход лимита дневного фида (getEventByPeriod ~2500/день).
    "refresh-subscribed-companies": {
        "task": "app.tasks.sync_tasks.refresh_subscribed_companies",
        "schedule": timedelta(seconds=settings.REFRESH_SUBSCRIBED_SCHEDULE_SECONDS),
        "args": (),
        "options": {"expires": int(settings.REFRESH_SUBSCRIBED_SCHEDULE_SECONDS * 0.8)},
    },
    # Полнота базы: сверка по состояниям (новые + сменившие статус по всей базе)
    "egr-reconcile-states": {
        "task": "app.tasks.sync_tasks.egr_reconcile_states",
        "schedule": timedelta(seconds=settings.EGR_RECONCILE_SCHEDULE_SECONDS),
        "args": (),
        "options": {"expires": int(settings.EGR_RECONCILE_SCHEDULE_SECONDS * 0.8)},
    },
}

# GRP в расписании только если включено (по умолчанию — ручной запуск)
if settings.GRP_SCHEDULE_ENABLED:
    _beat_schedule["grp-fetch-raw"] = {
        "task": "app.tasks.sync_tasks.grp_fetch_raw",
        "schedule": timedelta(seconds=settings.GRP_FETCH_SCHEDULE_SECONDS),
        "args": (settings.GRP_FETCH_LIMIT, settings.GRP_FETCH_BATCH_SIZE),
        "options": {"expires": int(settings.GRP_FETCH_SCHEDULE_SECONDS * 0.8)},
    }
    _beat_schedule["grp-process-raw"] = {
        "task": "app.tasks.sync_tasks.grp_process_raw",
        "schedule": timedelta(seconds=settings.GRP_PROCESS_SCHEDULE_SECONDS),
        "args": (settings.GRP_PROCESS_LIMIT,),
        "options": {"expires": int(settings.GRP_PROCESS_SCHEDULE_SECONDS * 0.8)},
    }

if settings.PVT_SCHEDULE_ENABLED:
    _beat_schedule["pvt-residents-sync"] = {
        "task": "app.tasks.park_tasks.sync_pvt_residents",
        "schedule": timedelta(seconds=settings.PVT_SYNC_SCHEDULE_SECONDS),
        "kwargs": {
            "limit": settings.PVT_SYNC_LIMIT,
            "batch_size": settings.PVT_SYNC_BATCH_SIZE,
            "delay": settings.PVT_SYNC_DELAY_SECONDS,
            "timeout": settings.PVT_SYNC_TIMEOUT_SECONDS,
            "only_missing": settings.PVT_SYNC_ONLY_MISSING,
        },
        "options": {"expires": settings.PVT_SYNC_SCHEDULE_SECONDS},
    }

# Пересборка агрегированных контактов компании — раз в сутки (тяжёлая очередь).
_beat_schedule["rebuild-company-contacts"] = {
    "task": "app.tasks.contacts_tasks.rebuild_company_contacts_task",
    "schedule": crontab(hour=5, minute=45),
    "args": (),
    "options": {"expires": 24 * 3600},
}

# Пересборка ключей текущих адресов ("компании по одному адресу") — раз в сутки.
_beat_schedule["rebuild-company-address-keys"] = {
    "task": "app.tasks.address_tasks.rebuild_company_address_keys_task",
    "schedule": crontab(hour=6, minute=15),
    "args": (),
    "options": {"expires": 24 * 3600},
}

# Ежемесячный экспорт GRP в JSON — всегда в расписании
_beat_schedule["grp-monthly-export"] = {
    "task": "app.tasks.sync_tasks.grp_monthly_export",
    "schedule": crontab(day_of_month=1, hour=6, minute=0),
    "args": (),
    "options": {"expires": 30 * 24 * 3600},
}

if not settings.GIAS_SYNC_ENABLED:
    _beat_schedule.pop("gias-sync-directory-registries", None)

# Keep-alive Битрикс-токена: принудительный refresh по расписанию, чтобы
# refresh_token не протух при простое (без вебхуков). По умолчанию раз в сутки.
if settings.BITRIX_KEEPALIVE_ENABLED:
    _beat_schedule["bitrix-token-keepalive"] = {
        "task": "app.tasks.bitrix_tasks.bitrix_token_keepalive",
        "schedule": timedelta(seconds=settings.BITRIX_KEEPALIVE_SCHEDULE_SECONDS),
        "args": (),
        "options": {"expires": int(settings.BITRIX_KEEPALIVE_SCHEDULE_SECONDS * 0.8)},
    }

# Bankrot.gov.by в расписании только если BANKROT_SCHEDULE_ENABLED=true
if settings.BANKROT_SCHEDULE_ENABLED:
    _beat_schedule["bankrot-sync-cases"] = {
        "task": "app.tasks.bankrot_tasks.sync_bankrot_cases",
        "schedule": timedelta(seconds=settings.BANKROT_SCHEDULE_SECONDS),
        "kwargs": {},
        "options": {"expires": settings.BANKROT_SCHEDULE_SECONDS},
    }

# Геокодинг адресов через OSM/Nominatim — только если включено (1 req/sec, идёт долго).
if settings.GEOCODE_SCHEDULE_ENABLED:
    _beat_schedule["egr-geocode-place-locations"] = {
        "task": "app.tasks.sync_tasks.egr_geocode_place_locations",
        "schedule": timedelta(seconds=settings.GEOCODE_SCHEDULE_SECONDS),
        "kwargs": {},
        "options": {"expires": int(settings.GEOCODE_SCHEDULE_SECONDS * 0.8)},
    }

if settings.LICENSE_SCHEDULE_ENABLED:
    _beat_schedule["license-check-changes"] = {
        "task": "app.tasks.license_tasks.check_license_changes",
        "schedule": timedelta(seconds=settings.LICENSE_SCHEDULE_SECONDS),
        "kwargs": {},
        "options": {"expires": settings.LICENSE_SCHEDULE_SECONDS},
    }

# ЕАЭС СЭЗ — резиденты СЭЗ (portal.eaeunion.org), только если включено.
if settings.SEZ_SCHEDULE_ENABLED:
    _beat_schedule["eaeu-sez-sync"] = {
        "task": "app.tasks.eaeu_sez_tasks.sync_eaeu_sez_residents",
        "schedule": timedelta(seconds=settings.SEZ_SCHEDULE_SECONDS),
        "kwargs": {},
        "options": {"expires": int(settings.SEZ_SCHEDULE_SECONDS * 0.8)},
    }

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone="Europe/Minsk",
    enable_utc=True,
    beat_schedule=_beat_schedule,
    broker_connection_retry_on_startup=True,

    # ------------------------------------------------------------------
    # Маршрутизация задач по очередям
    #
    # celery  — быстрые/частые задачи and EGR fetch/process pipeline
    # heavy   — long-running external sync jobs (historical, gias, bankrot, pvt)
    #
    # Цель: быстрые задачи никогда не ждут пока закончится GIAS/historical
    # ------------------------------------------------------------------
    task_routes={
        # ── Heavy queue ────────────────────────────────────────────────
        "app.tasks.sync_tasks.auto_fetch_historical_data":    {"queue": "heavy"},
        "app.tasks.sync_tasks.sync_gias_directory_registries": {"queue": "heavy"},
        "app.tasks.sync_tasks.grp_fetch_raw":                 {"queue": "heavy"},
        "app.tasks.sync_tasks.grp_monthly_export":            {"queue": "heavy"},
        "app.tasks.sync_tasks.reprocess_failed_rows":         {"queue": "heavy"},
        "app.tasks.sync_tasks.retry_failed_rows":             {"queue": "heavy"},
        "app.tasks.sync_tasks.refresh_subscribed_companies":  {"queue": "heavy"},
        "app.tasks.sync_tasks.egr_reconcile_states":          {"queue": "heavy"},
        "app.tasks.sync_tasks.reindex_elasticsearch":         {"queue": "heavy"},
        "app.tasks.sync_tasks.enrich_missing_raw":            {"queue": "heavy"},
        "app.tasks.bankrot_tasks.sync_bankrot_cases":         {"queue": "heavy"},
        "app.tasks.license_tasks.check_license_changes":      {"queue": "heavy"},
        "app.tasks.park_tasks.sync_pvt_residents":            {"queue": "heavy"},
        "app.tasks.contacts_tasks.rebuild_company_contacts_task": {"queue": "heavy"},
        "app.tasks.eaeu_sez_tasks.sync_eaeu_sez_residents":   {"queue": "heavy"},
        "app.tasks.address_tasks.rebuild_company_address_keys_task": {"queue": "heavy"},
        # ── Default (celery) queue — всё остальное ────────────────────
        # process_search_index_queue, grp_process_raw, egr_process_raw,
        # sync_daily_changes, load_companies_from_json,
        # update_reference_tables, egr_sync_place_locations, ...
    },
)
