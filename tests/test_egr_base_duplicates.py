"""The base-card API can repeat a card; conflicting snapshots are not duplicates."""
import asyncio
import json

import httpx
import pytest

from app.services.egr_client import EGRClient
from app.services.egr_contract import HistoryReconciliationError


UNP = 791462139
BASE = {"ngrn": UNP, "dfrom": "2026-10-12T21:00:00.000+00:00",
        "nsi00211": {"nkvob": 1}, "nsi00219": {"nksost": 1}}


def fetch(payload):
    paths = []
    async def check():
        def respond(request):
            paths.append(request.url.path)
            body = payload if "getBaseInfoByRegNum" in request.url.path else []
            return httpx.Response(200, text=json.dumps(body))
        client = EGRClient()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            return await client.get_full_company_history_strict(UNP, delay=0)
        finally:
            await client.close()
    return asyncio.run(check()), paths


@pytest.mark.parametrize("count", [2, 15, 100])
def test_exact_duplicates_are_normalized_without_losing_original_response(count):
    original = [dict(BASE) for _ in range(count)]
    result, paths = fetch(original)
    assert result["base_info"] == BASE
    assert result["base_info_response"] == original
    assert len(result["base_info_response"]) == count
    assert len(paths) == 5
    assert paths[-2].endswith(f"getAllJurNamesByRegNum/{UNP}")


def test_json_object_key_order_does_not_make_identical_rows_conflict():
    result, _ = fetch([BASE, dict(reversed(list(BASE.items())))])
    assert result["base_info"] == BASE and len(result["base_info_response"]) == 2


@pytest.mark.parametrize("payload", [BASE, [BASE]])
def test_existing_single_card_contract_is_unchanged(payload):
    result, _ = fetch(payload)
    assert result["base_info"] == BASE
    assert "base_info_response" not in result


@pytest.mark.parametrize("payload", [
    [], None, {}, [None], [BASE, None], [BASE, []],
    [BASE, {**BASE, "ngrn": UNP + 1}],
    [{**BASE, "ngrn": UNP + 1}] * 15,
])
def test_invalid_or_foreign_cards_are_rejected(payload):
    with pytest.raises(ValueError, match="Invalid EGR base info") as error:
        fetch(payload)
    assert not isinstance(error.value, HistoryReconciliationError)


@pytest.mark.parametrize("payload", [
    [BASE, {**BASE, "dfrom": "2026-10-13T21:00:00.000+00:00"}],
    [BASE, {**BASE, "nsi00219": {"nksost": 2}}],
    [BASE, {**BASE, "nsi00211": {"nkvob": 2}}],
    [BASE, {**BASE, "nsi00211": {"nkvob": True}}],
    [BASE, {**BASE, "nsi00211": {"nkvob": 1.0}}],
])
def test_differing_cards_for_the_same_unp_are_reconciliation_conflicts(payload):
    with pytest.raises(HistoryReconciliationError, match="Conflicting EGR base cards"):
        fetch(payload)


def test_identical_cards_do_not_hide_invalid_entity_type():
    with pytest.raises(ValueError, match="Unknown EGR entity type"):
        fetch([{**BASE, "nsi00211": {"nkvob": 9}}] * 15)


def test_duplicates_do_not_turn_a_failed_history_request_into_success():
    async def check():
        def respond(request):
            if "getBaseInfoByRegNum" in request.url.path:
                return httpx.Response(200, json=[BASE] * 15)
            return httpx.Response(503)
        client = EGRClient()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_full_company_history_strict(UNP, delay=0)
        finally:
            await client.close()
    asyncio.run(check())
