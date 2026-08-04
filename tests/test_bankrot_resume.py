from __future__ import annotations

from types import SimpleNamespace

import pytest
from billiard.exceptions import SoftTimeLimitExceeded

from app.services.bankrot_client import BankrotClient
from app.services.bankrot_sync import _resolve_resume_offset


def _client_without_http() -> BankrotClient:
    return object.__new__(BankrotClient)


def test_resume_offset_uses_persisted_cursor() -> None:
    run = SimpleNamespace(last_page=3, total_cases=999)
    assert _resolve_resume_offset(run, {"next_offset": 80}, 20) == (80, False)


def test_resume_offset_recovers_legacy_run_at_full_page_boundary() -> None:
    run = SimpleNamespace(last_page=0, total_cases=11_425)
    assert _resolve_resume_offset(
        run,
        {"duplicate_cases_skipped": 3},
        20,
    ) == (11_420, True)


def test_iter_all_cases_starts_from_saved_offset_and_checkpoints_page() -> None:
    client = _client_without_http()
    requested_offsets: list[int] = []
    checkpoints: list[tuple[int, int, int]] = []

    def get_page(*, offset: int, count: int, filters=None):
        requested_offsets.append(offset)
        assert count == 20
        return {"items": [{"id": 41}, {"id": 42}], "totalCount": 100}

    client.get_cases_page = get_page  # type: ignore[method-assign]

    rows = list(
        client.iter_all_cases(
            page_size=20,
            delay=0,
            start_offset=40,
            page_complete=lambda page, offset, total: (
                checkpoints.append((page, offset, total)) or False
            ),
        )
    )

    assert [row["id"] for row in rows] == [41, 42]
    assert requested_offsets == [40]
    assert checkpoints == [(3, 42, 100)]


def test_page_checkpoint_runs_only_after_page_is_fully_consumed() -> None:
    client = _client_without_http()
    checkpoints: list[tuple[int, int, int]] = []
    client.get_cases_page = lambda **kwargs: {  # type: ignore[method-assign]
        "items": [{"id": 1}, {"id": 2}],
        "count": 2,
    }

    iterator = client.iter_all_cases(
        page_size=20,
        delay=0,
        page_complete=lambda page, offset, total: (
            checkpoints.append((page, offset, total)) or True
        ),
    )

    assert next(iterator)["id"] == 1
    assert checkpoints == []
    assert next(iterator)["id"] == 2
    assert checkpoints == []
    with pytest.raises(StopIteration):
        next(iterator)
    assert checkpoints == [(1, 2, 2)]


def test_related_dataset_does_not_swallow_celery_soft_limit() -> None:
    client = _client_without_http()

    def raise_soft_limit(*args, **kwargs):
        raise SoftTimeLimitExceeded()

    client.get_case_dataset = raise_soft_limit  # type: ignore[method-assign]

    with pytest.raises(SoftTimeLimitExceeded):
        client.get_case_related_data(
            123,
            dataset_names={"properties"},
            page_size=20,
            max_pages=10,
            delay=0,
        )
