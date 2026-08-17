from app.services.unp_probe import DualProbeResult, SourceResult
from app.services import unp_scan_registry
from app.services.unp_scan_registry import (
    _frontier_scan_bounds,
    _probe_result_state,
)


def test_frontier_bounds_use_scan_window_not_historical_range_start() -> None:
    start, end = _frontier_scan_bounds(
        {
            "seq_start": 10,
            "seq_end": 900_000,
            "scan_start": 899_950,
            "scan_end": 900_050,
        },
        seq_start=0,
        seq_end=9_999_999,
    )

    assert (start, end) == (899_950, 900_050)


def test_one_confirmed_source_is_recorded_as_partial() -> None:
    result = DualProbeResult(
        unp="100074485",
        egr=SourceResult(source="egr", status="found", payload={"unp": 1}),
        grp=SourceResult(source="grp", status="not_found"),
    )

    assert _probe_result_state(result) == (
        "found",
        "not_found",
        "partial",
        True,
    )


def test_persistence_failure_is_not_recorded_as_verified_source() -> None:
    result = DualProbeResult(
        unp="100074485",
        egr=SourceResult(source="egr", status="found", payload={"unp": 1}),
        grp=SourceResult(source="grp", status="not_found"),
        persist_errors=("EGR persist: database unavailable",),
    )

    assert _probe_result_state(result) == (
        "error",
        "not_found",
        "error",
        False,
    )


def test_partial_result_records_next_recheck_delay(monkeypatch) -> None:
    recorded_rows = []

    class FakeSession:
        def execute(self, _statement, rows):
            recorded_rows.extend(rows)

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(unp_scan_registry, "SessionLocal", FakeSession)
    result = DualProbeResult(
        unp="100074485",
        egr=SourceResult(source="egr", status="found", payload={"unp": 1}),
        grp=SourceResult(source="grp", status="not_found"),
    )

    unp_scan_registry.record_probe_results(
        [result],
        partial_recheck_seconds=43_200,
    )

    assert recorded_rows[0]["overall_status"] == "partial"
    assert recorded_rows[0]["recheck_seconds"] == 43_200
