from datetime import date

from app.utils.company_age import company_age_days


def test_company_age_stops_at_liquidation() -> None:
    assert company_age_days(
        date(2014, 7, 21),
        date(2018, 8, 15),
        today=date(2026, 8, 14),
    ) == 1486


def test_active_company_age_uses_today() -> None:
    assert company_age_days(
        date(2014, 7, 21),
        None,
        today=date(2026, 8, 14),
    ) == 4407
