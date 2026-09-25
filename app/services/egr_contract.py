"""Conversions shared by the EGR mapper and its historical-key repair."""
from datetime import date, datetime
import pytz

MINSK = pytz.timezone("Europe/Minsk")


def egr_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        return value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.strptime(str(value), "%d.%m.%Y").date()
            except ValueError:
                return None
    return parsed.astimezone(MINSK).date() if parsed.tzinfo else parsed.date()


def lower_keys(value):
    if isinstance(value, dict):
        return {key.lower(): lower_keys(item) for key, item in value.items()}
    if isinstance(value, list):
        return [lower_keys(item) for item in value]
    return value


def period_fields(row):
    """Keep evidence of the former UTC-truncation key for an in-place repair."""
    start = egr_date(row.get("dfrom"))
    fields = {"valid_from": start, "valid_to": egr_date(row.get("dto"))}
    for source, target in (("dfrom", "valid_from"), ("dto", "valid_to")):
        try:
            old = date.fromisoformat(str(row.get(source))[:10])
        except ValueError:
            old = None
        if old and old != fields[target]:
            fields[f"_legacy_{target}"] = old
    return fields


def legacy_address_text(row):
    """Exact pre-contract mapper rendering, not fuzzy address normalization.

    Preserve settlement/street types: a village and an agrotown must not
    become interchangeable merely because their period dates coincide.
    """
    parts = []
    country = (row.get("nsi00201") or {}).get("vnstranp")
    if country and country != "Республика Беларусь":
        parts.append(country)
    if row.get("vregion"):
        parts.append(row["vregion"])
    for value, ref, field in (("vnp", "nsi00239", "vntnpk"), ("vulitsa", "nsi00226", "vntulk")):
        if row.get(value):
            parts.append(f"{(row.get(ref) or {}).get(field, '')} {row[value]}".strip())
    if row.get("vdom"):
        parts.append(f"д. {row['vdom']}")
    if row.get("vpom"):
        room_type = (row.get("nsi00234") or {}).get("vnvpom") or ""
        label = "оф." if "нежилое" in room_type.lower() else "кв."
        parts.append(f"{label} {row['vpom']}")
    return ", ".join(parts) if parts else None


def map_event(row):
    row = lower_keys(row)
    source_id = row.get("ngr04004")
    if isinstance(source_id, bool) or not str(source_id).isdigit():
        raise ValueError("EGR event without a valid source id")
    fields = {"event_record_id": int(source_id), "document_number": row.get("vdocn"), "notes": row.get("vprim")}
    for source, target in (("dfrom", "event_date"), ("dto", "cancel_date"), ("ddoc", "document_date"),
                           ("dsrok", "deadline_date"), ("dsrok2", "suspension_end_date")):
        fields[target] = egr_date(row.get(source))
    references = []
    for source, key, label, table, target in (
        ("nsi00223", "nkop", "vnop", "ref_events", "event_type_id"),
        ("nsi00212r", "nkuz", "vnuzp", "ref_authorities", "decision_authority_id"),
        ("nsi00212d", "nkuz", "vnuzp", "ref_authorities", "document_authority_id"),
        ("nsi00213", "nkosn", "vnosn", "ref_foundations", "foundation_id"),
    ):
        ref = row.get(source) or {}
        fields[target] = ref.get(key)
        if ref.get(key) is not None:
            references.append((table, ref[key], ref.get(label) or str(ref[key])))
    fields["_references"] = references
    return fields
