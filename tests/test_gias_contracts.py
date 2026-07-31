import threading
import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

from app.services.gias_contracts import GiasContractService


CONTRACT_ID = UUID("36943a2a-3718-45ce-869d-09a8c48b13f1")


def _service_without_network() -> GiasContractService:
    service = GiasContractService.__new__(GiasContractService)
    service.search_url = "https://gias.by/search/api/v1/search/contracts"
    service.detail_url = "https://gias.by/contract/api/v1/contract"
    service.page_size = 100
    service.timeout = 30.0
    service.history_start_ms = 1_546_300_800_000
    service.history_window_ms = 31 * 24 * 60 * 60 * 1000
    service.history_max_window_pages = 90
    service.history_min_window_ms = 60 * 60 * 1000
    service.session = Mock()
    return service


def test_index_request_uses_discovered_payload_and_update_sort() -> None:
    service = _service_without_network()
    response = Mock()
    response.json.return_value = {"content": [], "totalPages": 0}
    service.session.post.return_value = response

    payload = service._fetch_index_page(7)

    assert payload["content"] == []
    service.session.post.assert_called_once_with(
        service.search_url,
        json={
            "baseContractId": None,
            "page": 7,
            "pageSize": 100,
            "sortField": "dtUpdate",
            "sortOrder": "DESC",
        },
        timeout=30.0,
    )
    response.raise_for_status.assert_called_once()


def test_history_index_request_uses_millisecond_date_window() -> None:
    service = _service_without_network()
    response = Mock()
    response.json.return_value = {"content": [], "totalPages": 0}
    service.session.post.return_value = response

    service._fetch_index_page(
        3,
        created_from_ms=1_735_689_600_000,
        created_to_ms=1_735_776_000_000,
        sort_field="dtCreate",
        sort_order="ASC",
    )

    service.session.post.assert_called_once_with(
        service.search_url,
        json={
            "baseContractId": None,
            "page": 3,
            "pageSize": 100,
            "sortField": "dtCreate",
            "sortOrder": "ASC",
            "dtCreateFrom": 1_735_689_600_000,
            "dtCreateTo": 1_735_776_000_000,
        },
        timeout=30.0,
    )


def test_empty_gias_window_normalizes_null_content() -> None:
    service = _service_without_network()
    response = Mock()
    response.json.return_value = {
        "number": 0,
        "size": 100,
        "totalPages": 0,
        "totalElements": 0,
        "content": None,
        "first": True,
        "last": True,
    }
    service.session.post.return_value = response

    payload = service._fetch_index_page(
        0,
        created_from_ms=1_546_300_800_000,
        created_to_ms=1_548_979_199_999,
        sort_field="dtCreate",
        sort_order="ASC",
    )

    assert payload["content"] == []


def test_null_content_with_nonzero_total_is_rejected() -> None:
    service = _service_without_network()
    response = Mock()
    response.json.return_value = {
        "totalPages": 1,
        "totalElements": 1,
        "content": None,
    }
    service.session.post.return_value = response

    try:
        service._fetch_index_page(0)
    except ValueError as exc:
        assert "Unsupported GIAS contract search response" in str(exc)
    else:
        raise AssertionError("nonempty responses must contain a content list")


def test_summary_and_position_normalization() -> None:
    service = _service_without_network()
    summary = service._summary_values(
        {
            "customer": {
                "unp": "591875100",
                "name": "Заказчик",
                "location": "Минск",
            },
            "contractPrice": 2300,
            "contractPriceCurrencyCode": "BYN",
            "titleContract": "Работы",
            "dtUpdate": 1785136694210,
        }
    )
    position = service._normalize_position(
        CONTRACT_ID,
        {
            "id": "e090f906-fbd2-47ef-a495-d58a4615261b",
            "titlePosition": "Демонтаж",
            "okpb": {"code": "43.11.10.000", "name": "Работы по сносу"},
            "unitPrice": "2300.00",
            "positionPrice": 2300,
            "countryProducts": ["BY"],
            "countryProductsStr": ["Беларусь"],
        },
    )

    assert summary["customer_unp"] == 591875100
    assert summary["price"] == Decimal("2300")
    assert position is not None
    assert position.contract_id == CONTRACT_ID
    assert position.okpb_code == "43.11.10.000"
    assert position.position_price == Decimal("2300")
    assert position.countries == ["BY"]


def test_detail_response_must_match_requested_contract() -> None:
    service = _service_without_network()
    response = Mock()
    response.json.return_value = {
        "contractId": "11111111-1111-1111-1111-111111111111"
    }
    service.session.get.return_value = response

    try:
        service._fetch_detail(CONTRACT_ID)
    except ValueError as exc:
        assert "different contractId" in str(exc)
    else:
        raise AssertionError("mismatched contractId must be rejected")


def test_initial_index_resumes_from_durable_page_cursor() -> None:
    class QueryStub:
        def filter(self, *args):
            return self

        def all(self):
            return []

    class DBStub:
        def query(self, *args):
            return QueryStub()

        def commit(self):
            return None

        def rollback(self):
            return None

    state = SimpleNamespace(
        next_page=0,
        total_pages=None,
        initial_complete=False,
        history_window_start_ms=1_546_300_800_000,
        history_window_end_ms=1_546_387_200_000,
        history_target_ms=1_546_387_200_000,
    )
    requested_pages: list[tuple[int, int, int]] = []
    service = _service_without_network()
    service.page_size = 1
    service.db = DBStub()
    service._start_run = lambda registry: SimpleNamespace(status="running")
    service._get_sync_state = lambda reset: state
    service._upsert_summary = lambda payload, existing: "created"
    service._fetch_index_page = lambda page, **kwargs: (
        requested_pages.append(
            (page, kwargs["created_from_ms"], kwargs["created_to_ms"])
        )
        or {
            "content": [
                {
                    "contractId": (
                        f"00000000-0000-0000-0000-{page + 1:012d}"
                    ),
                    "dtUpdate": 1785136694210 - page,
                }
            ],
            "totalPages": 3,
        }
    )

    first = service.sync_index(max_pages=2)
    assert [item[0] for item in requested_pages] == [0, 1]
    assert first["pages"] == 2
    assert state.next_page == 2
    assert state.initial_complete is False

    second = service.sync_index(max_pages=2)
    assert [item[0] for item in requested_pages] == [0, 1, 2]
    assert second["pages"] == 1
    assert state.next_page == 0
    assert state.initial_complete is True


def test_history_window_is_split_before_api_page_cap() -> None:
    class DBStub:
        def commit(self):
            return None

    service = _service_without_network()
    service.db = DBStub()
    state = SimpleNamespace(
        next_page=0,
        total_pages=None,
        initial_complete=False,
        history_window_start_ms=1_700_000_000_000,
        history_window_end_ms=1_702_678_400_000,
        history_target_ms=1_702_678_400_000,
    )
    original_end = state.history_window_end_ms
    calls = 0
    requested_windows: list[tuple[int, int]] = []

    def fetch(page: int, **kwargs):
        nonlocal calls
        calls += 1
        requested_windows.append(
            (kwargs["created_from_ms"], kwargs["created_to_ms"])
        )
        if calls == 1:
            return {"content": [{"contractId": str(CONTRACT_ID)}], "totalPages": 140}
        return {"content": [], "totalPages": 0}

    service._fetch_index_page = fetch
    stats = SimpleNamespace(
        fetched=0,
        created=0,
        updated=0,
        unchanged=0,
        failed=0,
        pages=0,
    )

    service._sync_history_index(state, stats, max_pages=2)

    assert calls == 2
    assert requested_windows[1][1] < original_end - 1
    assert state.initial_complete is False


def test_empty_history_page_does_not_mark_full_sync_complete() -> None:
    class DBStub:
        def commit(self):
            return None

    service = _service_without_network()
    service.db = DBStub()
    state = SimpleNamespace(
        next_page=4,
        total_pages=20,
        initial_complete=False,
        history_window_start_ms=1_700_000_000_000,
        history_window_end_ms=1_700_086_400_000,
        history_target_ms=1_700_086_400_000,
    )
    service._fetch_index_page = lambda page, **kwargs: {
        "content": [],
        "totalPages": 20,
    }
    stats = SimpleNamespace(
        fetched=0,
        created=0,
        updated=0,
        unchanged=0,
        failed=0,
        pages=0,
    )

    try:
        service._sync_history_index(state, stats, max_pages=1)
    except RuntimeError as exc:
        assert "empty history page" in str(exc)
    else:
        raise AssertionError("premature empty pages must pause the backfill")

    assert state.initial_complete is False
    assert state.next_page == 4


def test_detail_scheduler_spaces_starts_and_caps_concurrency() -> None:
    service = _service_without_network()
    service.request_interval = 0.1
    service.detail_concurrency = 2
    service.request_delay = 0
    service._request_start_lock = threading.Lock()
    service._next_request_start = 0.0
    service._worker_session = lambda: object()
    starts: list[float] = []
    active = 0
    peak_active = 0
    lock = threading.Lock()

    def fake_fetch(_session: object, contract_id: UUID):
        nonlocal active, peak_active
        with lock:
            starts.append(time.monotonic())
            active += 1
            peak_active = max(peak_active, active)
        time.sleep(0.25)
        with lock:
            active -= 1
        return {"contractId": str(contract_id)}

    service._fetch_detail_with_session = fake_fetch
    rows = [
        SimpleNamespace(
            contract_id=UUID(f"00000000-0000-0000-0000-{index:012d}")
        )
        for index in range(1, 6)
    ]

    futures = service._schedule_detail_requests(rows)
    for row in rows:
        assert futures[row.contract_id].result()["contractId"] == str(
            row.contract_id
        )

    assert peak_active == 2
    assert len(starts) == 5
    assert all(
        later - earlier >= 0.08
        for earlier, later in zip(starts, starts[1:])
    )
