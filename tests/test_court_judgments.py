import app.services.court_judgments as court_module
import pytest
import requests
from app.services.court_judgments import (
    CourtJudgmentClient,
    CourtSearchFilters,
    parse_search_results,
)


SAMPLE = """
<div id="searchResultPage">
  <div>
    <h3><span class="number">Дело №151ЭИП24935 , Экономический суд Брестской области</span></h3>
    <div class="text"><span class="type">Тип:</span><p class="result">Решение</p></div>
    <div class="text"><span class="type">Дата вынесения:</span><p class="date-result">30.01.2025</p></div>
    <div><div class="readmore result"><p>Взыскать 100 рублей.</p><p><a href="/ru/juridical/judgmentresults/downloadresolution?processId=12657265&amp;docId=29067132">Скачать</a></p></div></div>
    <hr />
  </div>
  <ul id="SearchPages" class="pagination">
    <li class="active"><a href="#" data-page="1">1</a></li>
    <li><a href="#" data-page="8">8</a></li>
  </ul>
</div>
"""


def test_parse_search_results() -> None:
    records, pages = parse_search_results(SAMPLE, court_id=151, source_page=1)

    assert pages == 8
    assert len(records) == 1
    record = records[0]
    assert record.key == "document:29067132"
    assert record.case_number == "151ЭИП24935"
    assert record.court == "Экономический суд Брестской области"
    assert record.document_type == "Решение"
    assert record.judgment_date == "2025-01-30"
    assert record.resolution == "Взыскать 100 рублей."
    assert record.process_id == "12657265"
    assert record.document_id == "29067132"
    assert record.source_page == 1


def test_page_query_contains_search_and_pagination_fields() -> None:
    filters = CourtSearchFilters(
        date_from="01.01.2025",
        date_to="31.01.2025",
        court=151,
    )

    query = filters.page_query(3)

    assert query["Court"] == "151"
    assert query["TypeProc"] == "14"
    assert query["DateFrom"] == "01.01.2025"
    assert query["DateTo"] == "31.01.2025"
    assert query["CountRecords"] == "10"
    assert query["page"] == "3"
    assert "NumSuit" not in query
    assert "Name" not in query
    assert "CategoryDisput" not in query
    assert "TypeDispute" not in query


def test_page_query_keeps_active_optional_filters() -> None:
    filters = CourtSearchFilters(
        date_from="01.01.2025",
        date_to="31.01.2025",
        court=155,
        category_dispute=10,
        type_dispute=4,
        num_suit="123",
        name="Компания",
    )

    query = filters.page_query(2)

    assert query["CategoryDisput"] == "10"
    assert query["TypeDispute"] == "4"
    assert query["NumSuit"] == "123"
    assert query["Name"] == "Компания"


def test_client_parses_cookie_header_into_session_jar() -> None:
    client = CourtJudgmentClient(
        "ASP.NET_SessionId=session; .ASPXAUTH=auth",
        min_interval_seconds=600,
    )
    try:
        values = client.session.cookies.get_dict(domain="service.court.gov.by")
        assert values["ASP.NET_SessionId"] == "session"
        assert values[".ASPXAUTH"] == "auth"
        assert "Cookie" not in client.session.headers
    finally:
        client.close()


def test_client_persists_refreshed_cookie_values(tmp_path) -> None:
    cookie_file = tmp_path / "court.cookie"
    client = CourtJudgmentClient(
        "ASP.NET_SessionId=old; .ASPXAUTH=auth",
        cookie_file=cookie_file,
        min_interval_seconds=600,
    )
    try:
        client.session.cookies.set(
            "ASP.NET_SessionId",
            "renewed",
            domain="service.court.gov.by",
            path="/",
        )
        client._persist_cookies()
    finally:
        client.close()

    saved = cookie_file.read_text(encoding="utf-8")
    assert "ASP.NET_SessionId=renewed" in saved
    assert ".ASPXAUTH=auth" in saved


def test_client_loads_persisted_request_timestamp(tmp_path) -> None:
    state_file = tmp_path / ".court-request-rate.txt"
    state_file.write_text("1234.5\n", encoding="ascii")

    client = CourtJudgmentClient(
        "ASP.NET_SessionId=session; .ASPXAUTH=auth",
        rate_limit_state_file=state_file,
        min_interval_seconds=600,
    )
    try:
        assert client._last_request_started == 1234.5
    finally:
        client.close()


@pytest.mark.parametrize("interval, expected_wait", [(300, 250.0), (600, 550.0)])
def test_client_waits_for_persisted_minimum_interval(monkeypatch, interval, expected_wait) -> None:
    client = CourtJudgmentClient(
        "ASP.NET_SessionId=session; .ASPXAUTH=auth",
        min_interval_seconds=interval,
        delay_jitter_seconds=120,
    )
    waited = []
    client._last_request_started = 100.0
    monkeypatch.setattr(court_module.time, "time", lambda: 200.0)
    monkeypatch.setattr(court_module.time, "sleep", waited.append)
    monkeypatch.setattr(court_module.random, "uniform", lambda _start, _end: 50.0)
    try:
        client._wait_for_request_slot()
    finally:
        client.close()

    assert waited == [expected_wait]


@pytest.mark.parametrize("value", [
    "cookie\r\nASP.NET_SessionId=session; .ASPXAUTH=auth",
    "Cookie: ASP.NET_SessionId=session; .ASPXAUTH=auth",
])
def test_copied_cookie_label(value):
    with CourtJudgmentClient(value) as client:
        assert client.session.cookies.get(".ASPXAUTH") == "auth"


@pytest.mark.parametrize("interval", [0, 0.5, 299.9, float("nan"), float("inf")])
def test_short_or_invalid_intervals_rejected(interval):
    with pytest.raises(ValueError):
        CourtJudgmentClient("a=b", min_interval_seconds=interval)


def test_rate_state_corruption_stops_requests(tmp_path):
    path = tmp_path / "rate.txt"
    path.write_text("NaN")
    with pytest.raises(ValueError):
        CourtJudgmentClient("a=b", rate_limit_state_file=path)


@pytest.mark.parametrize("status", [302, 403, 429, 503])
def test_error_response_is_not_retried(monkeypatch, status):
    with CourtJudgmentClient("a=b") as client:
        calls = []
        def request(*args, **kwargs):
            calls.append(kwargs)
            response = requests.Response()
            response.status_code = status
            response.url = court_module.BASE_URL
            response._content = b""
            return response
        monkeypatch.setattr(client.session, "request", request)
        with pytest.raises((RuntimeError, requests.HTTPError)):
            client.fetch_page(CourtSearchFilters("01.01.2025", "31.01.2025", 151), 1)
        assert len(calls) == 1
        assert calls[0]["allow_redirects"] is False


def test_offsite_document_never_receives_cookie(monkeypatch, tmp_path):
    with CourtJudgmentClient("a=b") as client:
        def unexpected(*args, **kwargs):
            pytest.fail("Network should not be reached")
        monkeypatch.setattr(client.session, "request", unexpected)
        with pytest.raises(ValueError):
            client.download_document("https://other.example/document", tmp_path / "doc")


def test_blank_page_is_not_marked_success(monkeypatch):
    with CourtJudgmentClient("a=b") as client:
        response = requests.Response()
        response.status_code = 200
        response._content = b"\r\n"
        monkeypatch.setattr(client, "_request", lambda *args, **kwargs: response)
        with pytest.raises(RuntimeError):
            client.fetch_page(CourtSearchFilters("01.01.2025", "31.01.2025", 151), 2)
