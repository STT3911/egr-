"""Read-only address presentation shared by company profile responses."""
from __future__ import annotations

import re
from typing import Any, Iterable


_REGION = re.compile(
    r"(?:^|[,;]\s*)(Брестская|Витебская|Гомельская|Гродненская|Минская|Могил[её]вская)"
    r"(?:\s+(?:область|обл\.?)(?!\w)|(?=\s*,))",
    re.IGNORECASE,
)
_MINSK = re.compile(r"(?:^|[,;]\s*)(?:г\.?\s*Минск|Минск)(?=\s*[,;]|$)", re.IGNORECASE)
_POSTAL_CODE = re.compile(r"(?:^|[,;]\s*)(\d{6})(?=\s*[,;]|$)")
_DISTRICT = re.compile(
    r"(?:^|[,;]\s*)([А-ЯЁа-яё-]+)\s+(?:район|р-н)(?=\s*[,;]|$)",
    re.IGNORECASE,
)


def address_region(address: str | None) -> str | None:
    """Use explicit region text only; do not infer an oblast from a town name."""
    text = address or ""
    match = _REGION.search(text)
    if match:
        return match.group(1).capitalize().replace("ё", "е")
    if _MINSK.search(text):
        return "г. Минск"
    return None


def profile_addresses(history: Iterable[Any], place: Any = None) -> list[dict]:
    """Keep EGR periods intact; present a saved location only if history is absent.

    Fallback rows are observations, not invented EGR history. In particular,
    registration/fetch dates must never become address validity dates.
    """
    rows = [
        {
            "full_address": row.full_address,
            "postal_code": row.postal_code,
            "region": row.region or address_region(row.full_address),
            "district": row.district,
            "valid_from": row.valid_from.isoformat() if row.valid_from else None,
            "valid_to": row.valid_to.isoformat() if row.valid_to else None,
            "source": "egr",
        }
        for row in history
    ]
    if any((row["full_address"] or "").strip() for row in rows):
        return rows
    address = (getattr(place, "address", None) or "").strip()
    if not address:
        return rows

    raw = getattr(place, "raw_json", None)
    source = raw.get("source") if isinstance(raw, dict) else None
    if source is None:
        # Unlabelled placeLocation payloads come from the EGR Mobile API.
        source = "egr" if raw else None
    elif source not in ("grp", "gias", "egr"):
        source = None
    postal = _POSTAL_CODE.search(address)
    district = _DISTRICT.search(address)
    return [{
        "full_address": address,
        "postal_code": int(postal.group(1)) if postal else None,
        "region": address_region(address),
        "district": district.group(1) if district else None,
        "valid_from": None,
        "valid_to": None,
        "source": source,
    }]
