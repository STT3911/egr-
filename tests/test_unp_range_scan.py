from types import SimpleNamespace

from scripts.unp_enumerate import _summarize_range_candidates


def test_range_candidate_summary_combines_db_and_probe_results() -> None:
    candidates = [
        "100000001",
        "100000012",
        "100000023",
        "100000034",
    ]
    results = {
        "100000012": SimpleNamespace(outcome="hit"),
        "100000023": SimpleNamespace(outcome="miss"),
        "100000034": SimpleNamespace(outcome="error"),
    }

    summary = _summarize_range_candidates(
        candidates,
        egr_present={100000001, 100000012},
        grp_present={100000001},
        results_by_unp=results,
    )

    assert summary == (2, 1, 1)
