"""Helpers for resolving current company names without N+1 queries."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.database.models import Company, CompanyNameHistory


def get_company_names(db: Session, unps: Iterable[int]) -> dict[int, str]:
    numeric_unps = {int(unp) for unp in unps}
    if not numeric_unps:
        return {}

    rows = (
        db.query(
            Company.unp,
            CompanyNameHistory.full_name_ru,
            CompanyNameHistory.short_name_ru,
            CompanyNameHistory.full_name_by,
        )
        .join(CompanyNameHistory, CompanyNameHistory.company_id == Company.id)
        .filter(Company.unp.in_(numeric_unps))
        .order_by(
            Company.unp.asc(),
            CompanyNameHistory.valid_to.asc().nullsfirst(),
            CompanyNameHistory.valid_from.desc().nullslast(),
            CompanyNameHistory.id.desc(),
        )
        .all()
    )
    names: dict[int, str] = {}
    for unp, full_name_ru, short_name_ru, full_name_by in rows:
        name = full_name_ru or short_name_ru or full_name_by
        if name:
            names.setdefault(int(unp), name)
    return names
