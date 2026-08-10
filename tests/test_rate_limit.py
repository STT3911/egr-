import asyncio

from fastapi import HTTPException
from starlette.requests import Request

from app.core.security import _get_company_unp, rate_limit_check, rate_limiter
from app.core.config import settings


def _request(path: str, client_ip: str = "203.0.113.10") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": [(b"x-real-ip", client_ip.encode("ascii"))],
            "client": (client_ip, 50000),
            "server": ("tendex.test", 443),
        }
    )


def _reset_rate_limiter() -> None:
    with rate_limiter.lock:
        rate_limiter.requests.clear()
        rate_limiter.unique_items.clear()


def test_company_unp_is_shared_by_dossier_and_grp_routes() -> None:
    assert _get_company_unp(_request("/api/v1/companies/123456789")) == "123456789"
    assert (
        _get_company_unp(_request("/api/v1/companies/123456789/tax-debt"))
        == "123456789"
    )
    assert _get_company_unp(_request("/api/v1/grp/123456789")) == "123456789"
    assert _get_company_unp(_request("/api/v1/companies/lookup")) is None
    assert _get_company_unp(_request("/api/v1/grp/sync")) is None


def test_fifteen_company_pages_are_allowed_despite_six_requests_each() -> None:
    old_general = settings.RATE_LIMIT_PER_MINUTE
    old_companies = settings.RATE_LIMIT_COMPANIES_PER_MINUTE
    settings.RATE_LIMIT_PER_MINUTE = 180
    settings.RATE_LIMIT_COMPANIES_PER_MINUTE = 15
    _reset_rate_limiter()

    try:
        for index in range(15):
            unp = str(100_000_000 + index)
            paths = [
                f"/api/v1/companies/{unp}",
                f"/api/v1/grp/{unp}",
                f"/api/v1/companies/{unp}/tax-debt",
                f"/api/v1/companies/{unp}/related",
                f"/api/v1/companies/{unp}/risk",
                f"/api/v1/companies/{unp}/geocode",
            ]
            for path in paths:
                asyncio.run(rate_limit_check(_request(path)))

        # Repeating any endpoint for an already-counted company remains free
        # in the company quota (while still protected by the general ceiling).
        asyncio.run(rate_limit_check(_request("/api/v1/companies/100000000/risk")))
    finally:
        settings.RATE_LIMIT_PER_MINUTE = old_general
        settings.RATE_LIMIT_COMPANIES_PER_MINUTE = old_companies
        _reset_rate_limiter()


def test_sixteenth_distinct_company_is_rejected() -> None:
    old_general = settings.RATE_LIMIT_PER_MINUTE
    old_companies = settings.RATE_LIMIT_COMPANIES_PER_MINUTE
    settings.RATE_LIMIT_PER_MINUTE = 180
    settings.RATE_LIMIT_COMPANIES_PER_MINUTE = 15
    _reset_rate_limiter()

    try:
        for index in range(15):
            unp = str(200_000_000 + index)
            asyncio.run(rate_limit_check(_request(f"/api/v1/companies/{unp}")))

        try:
            asyncio.run(
                rate_limit_check(_request("/api/v1/companies/200000015"))
            )
        except HTTPException as exc:
            assert exc.status_code == 429
            assert exc.headers == {"Retry-After": "60"}
            assert "15 companies per minute" in exc.detail
        else:
            raise AssertionError("The sixteenth company lookup must be rejected")
    finally:
        settings.RATE_LIMIT_PER_MINUTE = old_general
        settings.RATE_LIMIT_COMPANIES_PER_MINUTE = old_companies
        _reset_rate_limiter()


def test_lookup_has_an_independent_request_bucket() -> None:
    old_general = settings.RATE_LIMIT_PER_MINUTE
    old_lookup = settings.RATE_LIMIT_LOOKUP_PER_MINUTE
    settings.RATE_LIMIT_PER_MINUTE = 10
    settings.RATE_LIMIT_LOOKUP_PER_MINUTE = 2
    _reset_rate_limiter()

    try:
        asyncio.run(rate_limit_check(_request("/api/v1/companies/lookup")))
        asyncio.run(rate_limit_check(_request("/api/v1/companies/lookup")))
        try:
            asyncio.run(rate_limit_check(_request("/api/v1/companies/lookup")))
        except HTTPException as exc:
            assert exc.status_code == 429
            assert "2 searches per minute" in exc.detail
        else:
            raise AssertionError("The lookup-specific limit must be enforced")
    finally:
        settings.RATE_LIMIT_PER_MINUTE = old_general
        settings.RATE_LIMIT_LOOKUP_PER_MINUTE = old_lookup
        _reset_rate_limiter()
