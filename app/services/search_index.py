"""Elasticsearch-backed company search index."""

from __future__ import annotations

import json
import re
import socket
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Any, Iterable

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import get_logger
from app.database.models import SystemState
from app.utils.search_normalizer import (
    keyboard_layout_query,
    normalize_company_name,
    transliterate_query,
)

logger = get_logger("services.search_index")

_LAST_ES_RESOLUTION_WARNING_AT = 0.0

# Кэш результата DNS-резолва хоста ES (TTL), чтобы не дёргать getaddrinfo на каждый поиск.
_RESOLUTION_TTL_SECONDS = 30.0
_resolution_cache = {"ok": False, "ts": 0.0}

# Переиспользуемый ES-клиент для горячего пути чтения (search_companies):
# строится один раз → keep-alive, без TCP/TLS-хендшейка на каждый запрос.
_shared_client = None

_REINDEX_STATE_KEY_PREFIX = "elasticsearch_reindex_v1"

try:
    from elasticsearch import Elasticsearch, helpers
except Exception:  # pragma: no cover - dependency may be absent before install
    Elasticsearch = None
    helpers = None


COMPANY_INDEX_BODY = {
    "settings": {
        "analysis": {
            "filter": {
                "autocomplete_filter": {
                    "type": "edge_ngram",
                    "min_gram": 2,
                    "max_gram": 20,
                }
            },
            "analyzer": {
                "autocomplete": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "autocomplete_filter"],
                },
                "autocomplete_search": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase"],
                },
            },
        }
    },
    "mappings": {
        "dynamic": False,
        "properties": {
            "company_id": {"type": "keyword"},
            "unp": {"type": "keyword"},
            "unp_text": {
                "type": "text",
                "analyzer": "autocomplete",
                "search_analyzer": "autocomplete_search",
            },
            "current_status_code": {"type": "integer"},
            "registration_date": {"type": "date", "ignore_malformed": True},
            "liquidation_date": {"type": "date", "ignore_malformed": True},
            "full_name_ru": {
                "type": "text",
                "analyzer": "autocomplete",
                "search_analyzer": "autocomplete_search",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
            },
            "short_name_ru": {
                "type": "text",
                "analyzer": "autocomplete",
                "search_analyzer": "autocomplete_search",
            },
            "full_name_by": {
                "type": "text",
                "analyzer": "autocomplete",
                "search_analyzer": "autocomplete_search",
            },
            "search_name": {
                "type": "text",
                "analyzer": "autocomplete",
                "search_analyzer": "autocomplete_search",
            },
            "all_names": {
                "type": "text",
                "analyzer": "autocomplete",
                "search_analyzer": "autocomplete_search",
            },
            "historical_names": {
                "type": "text",
                "analyzer": "autocomplete",
                "search_analyzer": "autocomplete_search",
            },
            "historical_search_names": {
                "type": "text",
                "analyzer": "autocomplete",
                "search_analyzer": "autocomplete_search",
            },
        },
    },
}


def _dedupe(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            continue
        text_value = str(value).strip()
        if not text_value or text_value in seen:
            continue
        seen.add(text_value)
        result.append(text_value)
    return result


def _is_elasticsearch_host_resolvable() -> bool:
    if not settings.ELASTICSEARCH_ENABLED:
        return False

    # Кэшируем результат на _RESOLUTION_TTL_SECONDS, чтобы не делать getaddrinfo
    # на каждый поисковый запрос (это заметная per-request латентность).
    now = time.monotonic()
    if now - _resolution_cache["ts"] < _RESOLUTION_TTL_SECONDS:
        return _resolution_cache["ok"]

    parsed = urlparse(settings.ELASTICSEARCH_URL)
    hostname = parsed.hostname
    if not hostname:
        _resolution_cache.update(ok=False, ts=now)
        return False

    try:
        socket.getaddrinfo(hostname, parsed.port or 9200, type=socket.SOCK_STREAM)
        _resolution_cache.update(ok=True, ts=now)
        return True
    except OSError as exc:
        _resolution_cache.update(ok=False, ts=now)
        global _LAST_ES_RESOLUTION_WARNING_AT
        if now - _LAST_ES_RESOLUTION_WARNING_AT >= 60:
            logger.warning(
                "Elasticsearch host %s is not resolvable right now: %s",
                hostname,
                exc,
            )
            _LAST_ES_RESOLUTION_WARNING_AT = now
        return False


def get_es_client():
    """Эфемерный клиент (для фоновых задач индексации; вызывающий код делает close())."""
    if (
        not settings.ELASTICSEARCH_ENABLED
        or Elasticsearch is None
        or not _is_elasticsearch_host_resolvable()
    ):
        return None
    return Elasticsearch(
        settings.ELASTICSEARCH_URL,
        request_timeout=settings.ELASTICSEARCH_REQUEST_TIMEOUT_SECONDS,
    )


def _get_shared_es_client():
    """
    Долгоживущий клиент для горячего пути поиска. Переиспользуется между запросами
    (keep-alive). НЕ закрывать после использования. Тред-безопасен.
    """
    global _shared_client
    if (
        not settings.ELASTICSEARCH_ENABLED
        or Elasticsearch is None
        or not _is_elasticsearch_host_resolvable()
    ):
        return None
    if _shared_client is None:
        _shared_client = Elasticsearch(
            settings.ELASTICSEARCH_URL,
            request_timeout=settings.ELASTICSEARCH_REQUEST_TIMEOUT_SECONDS,
        )
    return _shared_client


def enqueue_company_for_indexing(db: Session, unp: int, operation: str = "index") -> None:
    db.execute(
        text(
            """
            INSERT INTO search_index_queue (unp, operation, status, attempts, last_error, updated_at)
            VALUES (:unp, :operation, 'pending', 0, NULL, now())
            ON CONFLICT (unp) DO UPDATE SET
                operation = EXCLUDED.operation,
                status = 'pending',
                attempts = 0,
                last_error = NULL,
                updated_at = now()
            """
        ),
        {"unp": int(unp), "operation": operation},
    )


def has_pending_index_work(db: Session) -> bool:
    row = db.execute(
        text(
            """
            SELECT 1
            FROM search_index_queue
            WHERE status IN ('pending', 'failed')
            LIMIT 1
            """
        )
    ).first()
    return row is not None


def ping_elasticsearch() -> bool:
    client = get_es_client()
    if client is None:
        return False
    try:
        return bool(client.ping())
    except Exception as exc:
        logger.warning("Elasticsearch ping failed: %s", exc)
        return False
    finally:
        client.close()


def ensure_company_index(client=None) -> bool:
    client = client or get_es_client()
    if client is None:
        return False

    index_name = settings.ELASTICSEARCH_INDEX
    if client.indices.exists(index=index_name):
        return True

    client.indices.create(index=index_name, body=COMPANY_INDEX_BODY)
    logger.info("Created Elasticsearch index %s", index_name)
    return True


def get_index_status(db: Session | None = None) -> dict[str, Any]:
    client = get_es_client()
    queue_status = get_queue_status(db) if db is not None else None
    company_count = get_company_count(db) if db is not None else None
    if client is None:
        return {
            "enabled": settings.ELASTICSEARCH_ENABLED,
            "available": False,
            "queue": queue_status,
            "database_companies": company_count,
            "reindex": get_reindex_state(db),
        }
    try:
        index_name = settings.ELASTICSEARCH_INDEX
        available = bool(client.ping())
        exists = bool(client.indices.exists(index=index_name)) if available else False
        count = None
        if exists:
            count = client.count(index=index_name).get("count")
        return {
            "enabled": settings.ELASTICSEARCH_ENABLED,
            "available": available,
            "index": index_name,
            "exists": exists,
            "documents": count,
            "database_companies": company_count,
            "queue": queue_status,
            "reindex": get_reindex_state(db),
            "synced": bool(
                exists
                and queue_status
                and queue_status.get("outstanding") == 0
                and (company_count is None or count == company_count)
            ),
        }
    except Exception as exc:
        logger.warning("Elasticsearch status check failed: %s", exc)
        return {
            "enabled": settings.ELASTICSEARCH_ENABLED,
            "available": False,
            "index": settings.ELASTICSEARCH_INDEX,
            "database_companies": company_count,
            "queue": queue_status,
            "reindex": get_reindex_state(db),
            "synced": False,
            "error": str(exc),
        }
    finally:
        client.close()


def _reindex_state_key(index_name: str | None = None) -> str:
    return f"{_REINDEX_STATE_KEY_PREFIX}:{index_name or settings.ELASTICSEARCH_INDEX}"


def get_reindex_state(db: Session | None) -> dict[str, Any] | None:
    """Return the durable full-index progress marker for the configured index."""
    if db is None:
        return None

    row = db.get(SystemState, _reindex_state_key())
    if row is None:
        return None
    try:
        value = json.loads(row.value)
    except (TypeError, ValueError):
        logger.warning("Invalid Elasticsearch reindex state: %r", row.value)
        return None
    return value if isinstance(value, dict) else None


def _save_reindex_state(db: Session, state: dict[str, Any]) -> None:
    key = _reindex_state_key(state.get("index"))
    row = db.get(SystemState, key)
    value = json.dumps(state, ensure_ascii=False, default=str)
    if row is None:
        db.add(SystemState(key=key, value=value))
    else:
        row.value = value


def is_index_ready_for_search(db: Session | None) -> bool:
    """Use ES only after a complete full pass was verified against PostgreSQL."""
    state = get_reindex_state(db)
    return bool(
        state
        and state.get("index") == settings.ELASTICSEARCH_INDEX
        and state.get("status") == "complete"
        and state.get("synced") is True
    )


def get_company_count(db: Session | None) -> int | None:
    if db is None:
        return None
    return int(db.execute(text("SELECT COUNT(*) FROM egr_companies")).scalar() or 0)


def get_queue_status(db: Session | None) -> dict[str, Any] | None:
    if db is None:
        return None

    rows = db.execute(
        text(
            """
            SELECT status, COUNT(*) AS count
            FROM search_index_queue
            GROUP BY status
            """
        )
    ).mappings().all()
    counts = {row["status"]: int(row["count"]) for row in rows}
    outstanding = counts.get("pending", 0) + counts.get("failed", 0)

    oldest = db.execute(
        text(
            """
            SELECT MIN(updated_at) AS oldest_outstanding_at
            FROM search_index_queue
            WHERE status IN ('pending', 'failed')
            """
        )
    ).mappings().first()

    return {
        "counts": counts,
        "outstanding": outstanding,
        "oldest_outstanding_at": (
            oldest["oldest_outstanding_at"].isoformat()
            if oldest and oldest["oldest_outstanding_at"]
            else None
        ),
    }


def _company_rows(db: Session, *, last_unp: int = -1, limit: int = 1000):
    sql = text(
        """
        WITH company_page AS MATERIALIZED (
            SELECT
                id,
                unp,
                current_status_code,
                registration_date,
                liquidation_date
            FROM egr_companies
            WHERE unp > :last_unp
            ORDER BY unp ASC
            LIMIT :limit
        )
        SELECT
            c.id::text AS company_id,
            c.unp,
            c.current_status_code,
            c.registration_date,
            c.liquidation_date,
            current_n.full_name_ru,
            current_n.short_name_ru,
            current_n.full_name_by,
            current_n.search_name,
            array_remove(array_agg(DISTINCT hist_n.full_name_ru), NULL) AS historical_full_names,
            array_remove(array_agg(DISTINCT hist_n.short_name_ru), NULL) AS historical_short_names,
            array_remove(array_agg(DISTINCT hist_n.full_name_by), NULL) AS historical_full_names_by,
            array_remove(array_agg(DISTINCT hist_n.search_name), NULL) AS historical_search_names
        FROM company_page c
        LEFT JOIN LATERAL (
            SELECT
                n.full_name_ru,
                n.short_name_ru,
                n.full_name_by,
                n.search_name
            FROM egr_company_names_history n
            WHERE n.company_id = c.id
            ORDER BY
                (n.valid_to IS NULL) DESC,
                n.valid_to DESC NULLS LAST,
                n.valid_from DESC NULLS LAST
            LIMIT 1
        ) current_n ON TRUE
        LEFT JOIN egr_company_names_history hist_n
            ON hist_n.company_id = c.id
           AND hist_n.valid_to IS NOT NULL
        GROUP BY
            c.id,
            c.unp,
            c.current_status_code,
            c.registration_date,
            c.liquidation_date,
            current_n.full_name_ru,
            current_n.short_name_ru,
            current_n.full_name_by,
            current_n.search_name
        ORDER BY c.unp ASC
        """
    )
    return db.execute(sql, {"last_unp": last_unp, "limit": limit}).mappings().all()


def _company_row_by_unp(db: Session, unp: int):
    sql = text(
        """
        SELECT
            c.id::text AS company_id,
            c.unp,
            c.current_status_code,
            c.registration_date,
            c.liquidation_date,
            current_n.full_name_ru,
            current_n.short_name_ru,
            current_n.full_name_by,
            current_n.search_name,
            array_remove(array_agg(DISTINCT hist_n.full_name_ru), NULL) AS historical_full_names,
            array_remove(array_agg(DISTINCT hist_n.short_name_ru), NULL) AS historical_short_names,
            array_remove(array_agg(DISTINCT hist_n.full_name_by), NULL) AS historical_full_names_by,
            array_remove(array_agg(DISTINCT hist_n.search_name), NULL) AS historical_search_names
        FROM egr_companies c
        LEFT JOIN LATERAL (
            SELECT
                n.full_name_ru,
                n.short_name_ru,
                n.full_name_by,
                n.search_name
            FROM egr_company_names_history n
            WHERE n.company_id = c.id
            ORDER BY
                (n.valid_to IS NULL) DESC,
                n.valid_to DESC NULLS LAST,
                n.valid_from DESC NULLS LAST
            LIMIT 1
        ) current_n ON TRUE
        LEFT JOIN egr_company_names_history hist_n
            ON hist_n.company_id = c.id
           AND hist_n.valid_to IS NOT NULL
        WHERE c.unp = :unp
        GROUP BY
            c.id,
            c.unp,
            c.current_status_code,
            c.registration_date,
            c.liquidation_date,
            current_n.full_name_ru,
            current_n.short_name_ru,
            current_n.full_name_by,
            current_n.search_name
        LIMIT 1
        """
    )
    return db.execute(sql, {"unp": unp}).mappings().first()


def _date_to_iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def _mark_unps_indexed(db: Session, unps: list[int]) -> None:
    if not unps:
        return
    stmt = text(
        """
        UPDATE search_index_queue
        SET status = 'indexed',
            attempts = 0,
            last_error = NULL,
            indexed_at = now(),
            updated_at = now()
        WHERE unp IN :unps
        """
    ).bindparams(bindparam("unps", expanding=True))
    db.execute(stmt, {"unps": [int(unp) for unp in unps]})


def _mark_unp_failed(db: Session, unp: int, error: str) -> None:
    db.execute(
        text(
            """
            UPDATE search_index_queue
            SET status = 'failed',
                attempts = attempts + 1,
                last_error = :error,
                updated_at = now()
            WHERE unp = :unp
            """
        ),
        {"unp": int(unp), "error": error[:1000]},
    )


def company_document(row) -> dict[str, Any]:
    historical_names = _dedupe(
        list(row["historical_full_names"] or [])
        + list(row["historical_short_names"] or [])
        + list(row["historical_full_names_by"] or [])
    )
    historical_search_names = _dedupe(row["historical_search_names"] or [])
    current_names = _dedupe(
        [row["full_name_ru"], row["short_name_ru"], row["full_name_by"]]
    )

    return {
        "company_id": row["company_id"],
        "unp": str(row["unp"]),
        "unp_text": str(row["unp"]),
        "current_status_code": row["current_status_code"],
        "registration_date": _date_to_iso(row["registration_date"]),
        "liquidation_date": _date_to_iso(row["liquidation_date"]),
        "full_name_ru": row["full_name_ru"],
        "short_name_ru": row["short_name_ru"],
        "full_name_by": row["full_name_by"],
        "search_name": row["search_name"],
        "all_names": _dedupe(current_names + historical_names),
        "historical_names": historical_names,
        "historical_search_names": historical_search_names,
    }


def index_company_by_unp(db: Session, unp: int) -> bool:
    client = get_es_client()
    if client is None:
        return False
    try:
        if not client.ping():
            return False
        ensure_company_index(client)
        row = _company_row_by_unp(db, unp)
        if not row:
            return False
        client.index(
            index=settings.ELASTICSEARCH_INDEX,
            id=str(row["unp"]),
            document=company_document(row),
        )
        client.indices.refresh(index=settings.ELASTICSEARCH_INDEX)
        _mark_unps_indexed(db, [int(row["unp"])])
        return True
    except Exception as exc:
        logger.warning("Failed to index company %s: %s", unp, exc)
        return False
    finally:
        client.close()


def reindex_companies(
    db: Session,
    *,
    batch_size: int | None = None,
    limit: int | None = None,
    recreate: bool = False,
    resume: bool = True,
) -> dict[str, Any]:
    if helpers is None:
        raise RuntimeError("elasticsearch package is not installed")

    client = get_es_client()
    if client is None:
        raise RuntimeError("Elasticsearch is disabled")

    batch_size = batch_size or settings.ELASTICSEARCH_REINDEX_BATCH_SIZE
    indexed_this_run = 0
    indexed_total = 0
    last_unp = -1
    index_name = settings.ELASTICSEARCH_INDEX
    started_at = datetime.now(timezone.utc).isoformat()

    previous_state = get_reindex_state(db)
    if (
        resume
        and not recreate
        and previous_state
        and previous_state.get("index") == index_name
        and previous_state.get("status") in {"running", "partial", "failed"}
    ):
        last_unp = int(previous_state.get("last_unp", -1))
        indexed_total = int(previous_state.get("indexed_total", 0))
        started_at = previous_state.get("started_at") or started_at

    resumed_from_unp = last_unp
    exhausted_database = False

    try:
        if not client.ping():
            raise RuntimeError(f"Elasticsearch is not available at {settings.ELASTICSEARCH_URL}")

        if recreate and client.indices.exists(index=index_name):
            client.indices.delete(index=index_name)
        ensure_company_index(client)

        _save_reindex_state(
            db,
            {
                "index": index_name,
                "status": "running",
                "synced": False,
                "last_unp": last_unp,
                "indexed_total": indexed_total,
                "started_at": started_at,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        db.commit()

        while True:
            remaining = None if limit is None else max(limit - indexed_this_run, 0)
            if remaining == 0:
                break

            page_size = min(batch_size, remaining) if remaining else batch_size
            rows = _company_rows(db, last_unp=last_unp, limit=page_size)
            if not rows:
                exhausted_database = True
                break

            actions = (
                {
                    "_op_type": "index",
                    "_index": index_name,
                    "_id": str(row["unp"]),
                    "_source": company_document(row),
                }
                for row in rows
            )
            success, _ = helpers.bulk(
                client,
                actions,
                chunk_size=batch_size,
                request_timeout=max(settings.ELASTICSEARCH_REQUEST_TIMEOUT_SECONDS, 60),
            )
            _mark_unps_indexed(db, [int(row["unp"]) for row in rows])
            indexed_this_run += success
            indexed_total += success
            last_unp = int(rows[-1]["unp"])
            _save_reindex_state(
                db,
                {
                    "index": index_name,
                    "status": "running",
                    "synced": False,
                    "last_unp": last_unp,
                    "indexed_total": indexed_total,
                    "started_at": started_at,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            db.commit()
            logger.info(
                "Indexed %s companies into %s (cursor=%s, this_run=%s)",
                indexed_total,
                index_name,
                last_unp,
                indexed_this_run,
            )

        client.indices.refresh(index=index_name)
        database_count = get_company_count(db)
        document_count = int(client.count(index=index_name).get("count") or 0)
        synced = bool(exhausted_database and document_count == database_count)
        final_status = "complete" if synced else "partial"
        final_state = {
            "index": index_name,
            "status": final_status,
            "synced": synced,
            "last_unp": last_unp,
            "indexed_total": indexed_total,
            "database_companies": database_count,
            "documents": document_count,
            "started_at": started_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if synced:
            final_state["completed_at"] = datetime.now(timezone.utc).isoformat()
        _save_reindex_state(db, final_state)
        db.commit()
        return {
            "index": index_name,
            "indexed": indexed_this_run,
            "indexed_total": indexed_total,
            "last_unp": last_unp,
            "resumed_from_unp": resumed_from_unp,
            "recreated": recreate,
            "status": final_status,
            "synced": synced,
            "database_companies": database_count,
            "documents": document_count,
        }
    except Exception as exc:
        db.rollback()
        try:
            _save_reindex_state(
                db,
                {
                    "index": index_name,
                    "status": "failed",
                    "synced": False,
                    "last_unp": last_unp,
                    "indexed_total": indexed_total,
                    "started_at": started_at,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(exc)[:1000],
                },
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to persist Elasticsearch reindex failure state")
        raise
    finally:
        client.close()


def process_search_index_queue(db: Session, limit: int | None = None) -> dict[str, int]:
    client = get_es_client()
    if client is None:
        return {"processed": 0, "indexed": 0, "deleted": 0, "failed": 0}

    limit = limit or settings.ELASTICSEARCH_QUEUE_BATCH_SIZE
    indexed = 0
    deleted = 0
    failed = 0

    try:
        if not client.ping():
            return {"processed": 0, "indexed": 0, "deleted": 0, "failed": 0}
        ensure_company_index(client)

        queue_rows = db.execute(
            text(
                """
                SELECT unp, operation
                FROM search_index_queue
                WHERE status IN ('pending', 'failed')
                  AND attempts < :max_attempts
                ORDER BY updated_at ASC
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
                """
            ),
            {
                "limit": limit,
                "max_attempts": settings.ELASTICSEARCH_QUEUE_MAX_ATTEMPTS,
            },
        ).mappings().all()

        for queue_row in queue_rows:
            unp = int(queue_row["unp"])
            try:
                if queue_row["operation"] == "delete":
                    client.options(ignore_status=[404]).delete(
                        index=settings.ELASTICSEARCH_INDEX,
                        id=str(unp),
                    )
                    _mark_unps_indexed(db, [unp])
                    deleted += 1
                    continue

                row = _company_row_by_unp(db, unp)
                if not row:
                    client.options(ignore_status=[404]).delete(
                        index=settings.ELASTICSEARCH_INDEX,
                        id=str(unp),
                    )
                    _mark_unps_indexed(db, [unp])
                    deleted += 1
                    continue

                client.index(
                    index=settings.ELASTICSEARCH_INDEX,
                    id=str(row["unp"]),
                    document=company_document(row),
                )
                _mark_unps_indexed(db, [unp])
                indexed += 1
            except Exception as exc:
                failed += 1
                _mark_unp_failed(db, unp, str(exc))

        if indexed or deleted:
            client.indices.refresh(index=settings.ELASTICSEARCH_INDEX)
        db.commit()
        return {
            "processed": len(queue_rows),
            "indexed": indexed,
            "deleted": deleted,
            "failed": failed,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        client.close()


_CURRENT_NAME_FIELDS = [
    "search_name^8",
    "full_name_ru^6",
    "short_name_ru^5",
    "full_name_by^4",
]

_HISTORICAL_NAME_FIELDS = [
    "historical_names^2",
    "historical_search_names^2",
]

_CURRENT_RAW_NAME_FIELDS = [
    "full_name_ru^3",
    "short_name_ru^2.5",
    "full_name_by^2",
]

_HISTORICAL_RAW_NAME_FIELDS = ["historical_names"]


def _name_multi_match(
    query_text: str,
    fields: list[str],
    *,
    query_name: str,
) -> dict[str, Any]:
    """Build a precise name query, with optional typo tolerance."""
    clause: dict[str, Any] = {
        "query": query_text,
        "fields": fields,
        "type": "best_fields",
        # A company name query is a conjunction: for "минск строй" both
        # tokens must be present. The previous OR default allowed a match on
        # either common word and was the main source of noisy suggestions.
        "operator": "and",
        "_name": query_name,
    }
    if settings.ELASTICSEARCH_FUZZY_SEARCH:
        clause.update(fuzziness="AUTO", prefix_length=2, max_expansions=10)
    return {"multi_match": clause}


def search_companies(query: str, limit: int = 10) -> list[dict[str, Any]] | None:
    # Горячий путь: переиспользуемый клиент (keep-alive), НЕ закрываем его.
    client = _get_shared_es_client()
    if client is None:
        return None

    cleaned_query = re.sub(r"[\s-]", "", query.strip())
    normalized_query = normalize_company_name(query) or query.lower().strip()
    should: list[dict[str, Any]] = []

    if cleaned_query.isdigit():
        should.extend(
            [
                {"term": {"unp": {"value": cleaned_query, "boost": 20}}},
                {"prefix": {"unp": {"value": cleaned_query, "boost": 12}}},
                {"match": {"unp_text": {"query": cleaned_query, "boost": 8}}},
            ]
        )

    # Поля уже проиндексированы edge-ngram, поэтому обычный multi_match даёт
    # префиксный автокомплит дёшево. Фразовые запросы (match_phrase/_prefix) по
    # ngram-полям убраны — они дорогие и приводили к таймауту _search.
    # Fuzzy опционален (settings.ELASTICSEARCH_FUZZY_SEARCH): дорого и нестабильно
    # поверх ngram, по умолчанию выключен ради скорости.
    should.extend(
        [
            _name_multi_match(
                normalized_query,
                _CURRENT_NAME_FIELDS,
                query_name="current_normalized",
            ),
            _name_multi_match(
                normalized_query,
                _HISTORICAL_NAME_FIELDS,
                query_name="historical_normalized",
            ),
        ]
    )

    # Normalization intentionally removes the legal form. Use the raw query as
    # a secondary signal so "ООО Ромашка" still prefers ООО over an otherwise
    # equally relevant ИП/ОАО, without making the legal form mandatory.
    raw_query = query.lower().strip()
    if raw_query and raw_query != normalized_query:
        should.extend(
            [
                _name_multi_match(
                    raw_query,
                    _CURRENT_RAW_NAME_FIELDS,
                    query_name="current_raw",
                ),
                _name_multi_match(
                    raw_query,
                    _HISTORICAL_RAW_NAME_FIELDS,
                    query_name="historical_raw",
                ),
            ]
        )

    # Транслитерация лат<->кир: "minsk" -> "минск" и наоборот.
    translit = transliterate_query(query)
    if translit:
        translit_normalized = normalize_company_name(translit) or translit
        should.extend(
            [
                _name_multi_match(
                    translit_normalized,
                    _CURRENT_NAME_FIELDS,
                    query_name="current_translit",
                ),
                _name_multi_match(
                    translit_normalized,
                    _HISTORICAL_NAME_FIELDS,
                    query_name="historical_translit",
                ),
            ]
        )

    # Wrong keyboard layout is not transliteration: "vbycr" should also try
    # "минск". Keep the original query clauses, so real Latin names still work.
    keyboard_variant = keyboard_layout_query(query)
    if keyboard_variant:
        keyboard_normalized = (
            normalize_company_name(keyboard_variant) or keyboard_variant
        )
        if keyboard_normalized not in {normalized_query, translit_normalized if translit else None}:
            should.extend(
                [
                    _name_multi_match(
                        keyboard_normalized,
                        _CURRENT_NAME_FIELDS,
                        query_name="current_keyboard",
                    ),
                    _name_multi_match(
                        keyboard_normalized,
                        _HISTORICAL_NAME_FIELDS,
                        query_name="historical_keyboard",
                    ),
                ]
            )

    # function_score: действующие компании (без даты ликвидации) поднимаем над
    # ликвидированными, не меняя базовую релевантность лексики.
    scored_query = {
        "function_score": {
            "query": {"bool": {"should": should, "minimum_should_match": 1}},
            "functions": [
                {"filter": {"bool": {"must_not": {"exists": {"field": "liquidation_date"}}}},
                 "weight": 1.5},
            ],
            "score_mode": "multiply",
            "boost_mode": "multiply",
        }
    }

    body = {
        "size": limit,
        "track_total_hits": False,
        "query": scored_query,
        "highlight": {
            "pre_tags": [""],
            "post_tags": [""],
            "fields": {
                "historical_names": {"number_of_fragments": 1},
                "all_names": {"number_of_fragments": 1},
            },
        },
    }

    try:
        response = client.search(index=settings.ELASTICSEARCH_INDEX, body=body)
    except Exception as exc:
        logger.warning("Elasticsearch search failed: %s", exc)
        return None

    results: list[dict[str, Any]] = []
    for hit in response.get("hits", {}).get("hits", []):
        source = hit.get("_source", {})
        highlight = hit.get("highlight", {})
        historical_highlight = highlight.get("historical_names") or []
        matched_queries = set(hit.get("matched_queries") or [])
        matched_current = any(name.startswith("current_") for name in matched_queries)
        matched_historical = any(
            name.startswith("historical_") for name in matched_queries
        )
        matched_name = historical_highlight[0] if historical_highlight else None
        if not matched_name and matched_historical and not matched_current:
            matched_name = next(iter(source.get("historical_names") or []), None)
        fallback_name = next(iter(source.get("all_names") or []), None)

        results.append(
            {
                "unp": int(source["unp"]),
                "full_name_ru": source.get("full_name_ru") or fallback_name,
                "short_name_ru": source.get("short_name_ru"),
                "full_name_by": source.get("full_name_by"),
                "matched_name": matched_name,
                "matched_historical_name": bool(matched_name and matched_historical),
            }
        )

    return results
