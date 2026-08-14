"""Company lifetime helpers shared by scoring and reports."""
from __future__ import annotations

from datetime import date


def company_age_days(
    registration_date: date,
    liquidation_date: date | None,
    *,
    today: date | None = None,
) -> int:
    """Return lifetime up to liquidation, or up to today while active."""
    end_date = liquidation_date or today or date.today()
    return (end_date - registration_date).days
