from types import SimpleNamespace

from scripts.unp_enumerate import _summarize_range_candidates


def test_range_candidate_summary_counts_only_current_source_checks() -> None:
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
        results_by_unp=results,
    )

    assert summary == (1, 1, 1)
