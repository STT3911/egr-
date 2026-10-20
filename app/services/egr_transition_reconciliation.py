"""Lossless quarantine for incomplete official IP -> legal entity rows.

No identifier is inferred from a name. Resolution requires one full source row
whose other fields exactly match the original observation on the same day.
"""
from __future__ import annotations

import hashlib
import json


SOURCE = "getIPtoJurByPeriod"
IDENTIFIERS = ("ipngrn", "ulngrn")


def valid_unp(value):
    return (not isinstance(value, bool) and str(value).isascii()
            and str(value).isdigit() and 0 < int(value) < 1_000_000_000)


def invalid_identifiers(row):
    return [field for field in IDENTIFIERS if not valid_unp(row.get(field))]


def row_digest(row):
    return hashlib.sha256(json.dumps(
        row, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def quarantine_rows(state, day, rows, now):
    """Keep every distinct incomplete raw observation, idempotently on replay."""
    queue = state.setdefault("transition_conflicts", {})
    for row in rows:
        invalid = invalid_identifiers(row)
        if not invalid:
            continue
        key = f"{day}:{row_digest(row)}"
        queue.setdefault(key, {
            "day": day, "source": SOURCE, "raw": row,
            "invalid_fields": invalid, "attempts": 0,
            "first_seen_at": now, "next_retry_at": now + 3600,
        })


def resolution_candidate(item, rows):
    """Ambiguous, disappeared or changed observations must remain unresolved."""
    original = item["raw"]
    invalid = set(item["invalid_fields"])
    expected = {key: value for key, value in original.items() if key not in invalid}
    candidates = {}
    for row in rows:
        if invalid_identifiers(row):
            continue
        comparable = {key: value for key, value in row.items() if key not in invalid}
        if comparable == expected:
            candidates[row_digest(row)] = row
    return next(iter(candidates.values())) if len(candidates) == 1 else None


def defer_conflict(item, now, *, error=None):
    item["attempts"] += 1
    item["last_checked_at"] = now
    item["next_retry_at"] = now + min(86400, 3600 * 2 ** min(item["attempts"], 5))
    if error:
        item["last_error"] = error
    else:
        item.pop("last_error", None)


def transient_source_error(exc):
    import httpx

    return (isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError))
            or isinstance(exc, httpx.HTTPStatusError)
            and (exc.response.status_code == 429 or 500 <= exc.response.status_code < 600))
