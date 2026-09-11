import pytest
import requests

from scripts.inspect_court_catalog import DiagnosticClient, SearchControls


def test_extracts_filters_and_dates_without_authentication_fields():
    parser = SearchControls()
    parser.feed('''
      <input name="__RequestVerificationToken" value="secret-token">
      <select name="Account"><option value="secret-account">Private</option></select>
      <select id="Court"><option value="0">All &amp; courts</option>
      <option value="151"> Brest </option></select>
      <input name="DateFrom" value="01.01.2025" min="01.01.2010">
    ''')
    assert parser.selects == {"Court": [
        {"value": "0", "label": "All & courts"},
        {"value": "151", "label": "Brest"},
    ]}
    assert parser.dates == [{"name": "DateFrom", "value": "01.01.2025", "min": "01.01.2010"}]


def test_redirect_diagnostic_preserves_stop_and_hides_query(capsys):
    response = requests.Response()
    response.status_code = 302
    response.url = "https://service.court.gov.by/ru/juridical/judgmentresults"
    response.headers["Location"] = "/ru/example?token=secret-value#private-fragment"
    with DiagnosticClient("test=unused") as client:
        with pytest.raises(RuntimeError):
            client._checked_response(response)
    output = capsys.readouterr().out
    assert "/ru/example" in output
    assert "secret-value" not in output
    assert "private-fragment" not in output
