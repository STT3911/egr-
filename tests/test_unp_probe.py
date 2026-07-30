import asyncio
from types import SimpleNamespace

from app.services.unp_probe import (
    DualProbeResult,
    SourceResult,
    _fetch_egr_once,
)


def test_partial_source_hit_is_a_hit() -> None:
    result = DualProbeResult(
        unp="100074485",
        egr=SourceResult(
            source="egr",
            status="error",
            error="ReadTimeout",
        ),
        grp=SourceResult(
            source="grp",
            status="found",
            payload={"VUNP": "100074485"},
        ),
    )

    assert result.outcome == "hit"
    assert result.new_found == 1


def test_persist_error_still_stops_candidate() -> None:
    result = DualProbeResult(
        unp="100074485",
        egr=SourceResult(source="egr", status="not_found"),
        grp=SourceResult(
            source="grp",
            status="found",
            payload={"VUNP": "100074485"},
        ),
        persist_errors=("GRP persist failed",),
    )

    assert result.outcome == "error"


def test_egr_204_does_not_call_mobile_fallback() -> None:
    class Response:
        status_code = 204

        def raise_for_status(self) -> None:
            raise AssertionError("204 must not call raise_for_status")

    class HttpClient:
        async def get(self, *_args, **_kwargs):
            return Response()

    class EgrClient:
        base_url = "https://egr.example"

        async def _get_client(self):
            return HttpClient()

    class MobileClient:
        base_url = "https://mobile.example"

        async def _get_client(self):
            raise AssertionError("mobile fallback must not be called")

    aggregator = SimpleNamespace(
        egr_client=EgrClient(),
        mobile_client=MobileClient(),
    )

    payload, source_variant = asyncio.run(
        _fetch_egr_once(aggregator, "100074485")
    )

    assert payload is None
    assert source_variant == "legacy"
