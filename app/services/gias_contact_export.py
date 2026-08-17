"""CSV export of contacts for companies from the GIAS accreditation registry."""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import Session

from app.database.models import CompanyContact, GiasAccreditedCustomer


SOURCE_ORDER = {"egr": 0, "mart": 1, "gias": 2, "pvt": 3, "manual": 4}
CSV_FIELDS = (
    "unp",
    "company_name",
    "contact",
    "sources",
    "accreditation_state",
    "accreditation_from",
    "accreditation_to",
)


@dataclass(frozen=True)
class ContactExportRow:
    unp: str
    company_name: str
    contact_type: str
    value: str
    value_norm: str
    source: str
    accreditation_state: str | None
    accreditation_from: datetime | None
    accreditation_to: datetime | None


def _date_text(value: datetime | None) -> str:
    return value.date().isoformat() if value else ""


def _source_sort_key(source: str) -> tuple[int, str]:
    return SOURCE_ORDER.get(source, len(SOURCE_ORDER)), source


def collapse_contact_rows(
    rows: Iterable[ContactExportRow],
) -> dict[str, list[dict[str, str]]]:
    """Deduplicate the same contact across sources while preserving provenance."""
    grouped: dict[tuple[str, str, str], dict[str, object]] = {}

    for row in rows:
        key = (row.unp, row.contact_type, row.value_norm)
        item = grouped.get(key)
        if item is None:
            item = {
                "unp": row.unp,
                "company_name": row.company_name,
                "contact": row.value,
                "sources": set(),
                "accreditation_state": row.accreditation_state or "",
                "accreditation_from": _date_text(row.accreditation_from),
                "accreditation_to": _date_text(row.accreditation_to),
                "contact_type": row.contact_type,
            }
            grouped[key] = item
        sources = item["sources"]
        assert isinstance(sources, set)
        sources.add(row.source)

    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    for item in grouped.values():
        sources = item.pop("sources")
        contact_type = str(item.pop("contact_type"))
        assert isinstance(sources, set)
        item["sources"] = "|".join(sorted(sources, key=_source_sort_key))
        result[contact_type].append({key: str(value) for key, value in item.items()})

    for contact_type in result:
        result[contact_type].sort(
            key=lambda item: (item["unp"].zfill(20), item["contact"].lower())
        )
    return dict(result)


def _iter_contact_rows(db: Session) -> Iterable[ContactExportRow]:
    query = (
        db.query(
            GiasAccreditedCustomer.unp,
            GiasAccreditedCustomer.name,
            GiasAccreditedCustomer.state,
            GiasAccreditedCustomer.dt_from,
            GiasAccreditedCustomer.dt_to,
            CompanyContact.contact_type,
            CompanyContact.value,
            CompanyContact.value_norm,
            CompanyContact.source,
        )
        .join(
            CompanyContact,
            CompanyContact.company_id == GiasAccreditedCustomer.company_id,
        )
        .filter(CompanyContact.contact_type.in_(("phone", "email")))
        .yield_per(2000)
    )

    for row in query:
        yield ContactExportRow(
            unp=str(row.unp),
            company_name=row.name,
            contact_type=row.contact_type,
            value=row.value,
            value_norm=row.value_norm,
            source=row.source,
            accreditation_state=row.state,
            accreditation_from=row.dt_from,
            accreditation_to=row.dt_to,
        )


def _write_csv(path: Path, rows: list[dict[str, str]], delimiter: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, delimiter=delimiter)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def export_gias_accredited_contacts(
    db: Session,
    output_dir: Path,
    *,
    delimiter: str = ";",
) -> dict[str, object]:
    """Write separate phone and email CSV files for GIAS-accredited companies."""
    if len(delimiter) != 1:
        raise ValueError("CSV delimiter must be exactly one character")

    accredited_companies = db.query(GiasAccreditedCustomer.id).count()
    grouped = collapse_contact_rows(_iter_contact_rows(db))
    phones = grouped.get("phone", [])
    emails = grouped.get("email", [])

    phone_path = output_dir / "gias_accredited_phones.csv"
    email_path = output_dir / "gias_accredited_emails.csv"
    _write_csv(phone_path, phones, delimiter)
    _write_csv(email_path, emails, delimiter)

    return {
        "status": "ok",
        "accredited_companies": accredited_companies,
        "phones": {
            "rows": len(phones),
            "companies": len({row["unp"] for row in phones}),
            "path": str(phone_path),
        },
        "emails": {
            "rows": len(emails),
            "companies": len({row["unp"] for row in emails}),
            "path": str(email_path),
        },
    }
