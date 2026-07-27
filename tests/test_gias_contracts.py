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
    )
    requested_pages: list[int] = []
    service = _service_without_network()
    service.page_size = 1
    service.db = DBStub()
    service._start_run = lambda registry: SimpleNamespace(status="running")
    service._get_sync_state = lambda reset: state
    service._upsert_summary = lambda payload, existing: "created"
    service._fetch_index_page = lambda page: (
        requested_pages.append(page)
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
    assert requested_pages == [0, 1]
    assert first["pages"] == 2
    assert state.next_page == 2
    assert state.initial_complete is False

    second = service.sync_index(max_pages=2)
    assert requested_pages == [0, 1, 2]
    assert second["pages"] == 1
    assert state.next_page == 0
    assert state.initial_complete is True


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
