"""Convert official EGR event rows into subscription feed notifications."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable

from app.services.subscription_events import (
    EVENT_DIRECTOR_CHANGED,
    EVENT_EGR_EVENT,
    emit_company_event,
)


# Belarus has used UTC+03:00 year-round throughout the source's relevant
# history. A fixed offset also keeps slim containers independent of tzdata.
_MINSK_TZ = timezone(timedelta(hours=3))
_DIRECTOR_EVENT_CODES = {21700}


def _first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _parse_event_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(_MINSK_TZ).replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if value in (None, ""):
        return None

    raw = str(value).strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.astimezone(_MINSK_TZ).replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        pass
    for pattern in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:10], pattern)
        except ValueError:
            continue
    return None


def _event_type_name(payload: dict[str, Any]) -> str | None:
    reference = payload.get("nsi00223")
    if isinstance(reference, dict):
        value = _first(
            reference,
            "vnop",
            "vnsob",
            "name",
            "title",
        )
        if value:
            return str(value).strip()
    elif reference not in (None, ""):
        return str(reference).strip()
    value = _first(payload, "event_name", "eventName", "vnsob", "vnop")
    return str(value).strip() if value else None


def _notification_event_type(payload: dict[str, Any]) -> str:
    """Map only confirmed EGR operation codes to product event types."""
    reference = payload.get("nsi00223")
    code = _first(reference, "nkop") if isinstance(reference, dict) else None
    try:
        if int(code) in _DIRECTOR_EVENT_CODES:
            return EVENT_DIRECTOR_CHANGED
    except (TypeError, ValueError):
        pass

    # Text fallback covers older/alternate payloads that omit nkop. Keep this
    # deliberately narrow: an unknown official operation remains egr_event.
    name = (_event_type_name(payload) or "").casefold()
    if "назначени" in name and "руководител" in name:
        return EVENT_DIRECTOR_CHANGED
    return EVENT_EGR_EVENT


def _source_key(unp: int, payload: dict[str, Any]) -> str:
    source_id = _first(
        payload,
        "NGR04004",
        "ngr04004",
        "event_record_id",
        "eventRecordId",
        "id",
    )
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    version = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    if source_id in (None, ""):
        source_id = "snapshot"
    # An EGR row may later receive a cancellation date, deadline or note. Keep
    # the upstream id for traceability and the payload version so such an update
    # creates exactly one new notification instead of being silently discarded.
    return f"egr:{int(unp)}:{str(source_id)[:64]}:{version}"


def _description(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    event_name = _event_type_name(payload)
    if event_name:
        parts.append(event_name)
    document_number = _first(payload, "vdocn", "document_number", "documentNumber")
    if document_number:
        parts.append(f"документ № {document_number}")
    notes = _first(payload, "vprim", "notes", "note")
    if notes:
        parts.append(str(notes).strip())
    cancel_date = _first(payload, "dto", "cancel_date", "cancelDate")
    if cancel_date:
        parts.append(f"дата отмены: {cancel_date}")
    return "; ".join(part for part in parts if part) or "Новое событие в ЕГР"


def emit_egr_source_events(
    db: Any,
    unp: int,
    rows: Iterable[dict[str, Any]] | None,
    *,
    fallback_date: date | datetime | None = None,
) -> int:
    """Emit newly observed official EGR rows with deterministic deduplication.

    Per-UNP EGR responses contain historical rows, so occurrence time is passed
    to ``emit_company_event``. That function suppresses rows older than each
    subscription and the source key prevents replays on later hourly refreshes.
    """

    created = 0
    fallback = _parse_event_datetime(fallback_date)
    for payload in rows or ():
        if not isinstance(payload, dict):
            continue
        # dto is an actual later cancellation of an existing event. ddoc is
        # intentionally not used for occurrence: production contains invalid
        # future document dates (for example 2029 on a 2024 event).
        occurred_at = _parse_event_datetime(
            _first(payload, "dto", "cancel_date", "cancelDate")
        ) or _parse_event_datetime(
            _first(payload, "dfrom", "event_date", "eventDate")
        ) or fallback
        if occurred_at is None:
            # A historical response without a date cannot be safely separated
            # from pre-subscription history, so do not create a misleading alert.
            continue
        created += emit_company_event(
            db,
            unp,
            _notification_event_type(payload),
            new_value=_description(payload),
            occurred_at=occurred_at,
            source_key=_source_key(int(unp), payload),
        )
    return created
