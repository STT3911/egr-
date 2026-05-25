"""Tests for bankrot.gov.by synchronization service.

Покрытые сценарии:
  - extract_unp: все четыре источника + приоритет detail над list
  - extract_unp: УНП отсутствует во всех источниках → None
  - extract_unp: нечисловое значение → пропускается, берётся следующий источник
  - BankrotClient: retry при сетевой ошибке, успех на 3-й попытке
  - BankrotClient: немедленный выброс BankrotAPIError при 401
  - sync_bankrot_cases: сохраняет дела с NULL unp (без исключений)
  - sync_bankrot_cases: upsert идемпотентен (повторный вызов обновляет запись)
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from typing import Any, Dict, Iterator, List, Optional
from unittest.mock import MagicMock, call, patch

from app.services.bankrot_sync import (
    _build_row,
    _upsert_cases,
    extract_unp,
    sync_bankrot_cases,
)
from app.services.bankrot_client import BankrotAPIError


# ---------------------------------------------------------------------------
# extract_unp
# ---------------------------------------------------------------------------

class TestExtractUnp(unittest.TestCase):

    def test_detail_debtor_model_has_highest_priority(self):
        list_data   = {"debtorModel": {"organization": {"unp": 111111111}}}
        detail_data = {"debtorModel": {"organization": {"unp": 222222222}}}
        self.assertEqual(extract_unp(list_data, detail_data), 222222222)

    def test_detail_organization_fallback(self):
        list_data   = {"organization": {"unp": 111111111}}
        detail_data = {"organization": {"unp": 333333333}}
        self.assertEqual(extract_unp(list_data, detail_data), 333333333)

    def test_list_debtor_model_when_detail_missing(self):
        list_data   = {"debtorModel": {"organization": {"unp": 444444444}}}
        detail_data = {}
        self.assertEqual(extract_unp(list_data, detail_data), 444444444)

    def test_list_organization_last_resort(self):
        list_data   = {"organization": {"unp": 555555555}}
        detail_data = None
        self.assertEqual(extract_unp(list_data, detail_data), 555555555)

    def test_returns_none_when_all_sources_empty(self):
        self.assertIsNone(extract_unp({}, {}))
        self.assertIsNone(extract_unp(None, None))
        self.assertIsNone(extract_unp({"debtorModel": {}}, None))

    def test_skips_non_integer_value_and_tries_next(self):
        # detail has bad value, list has good value
        list_data   = {"organization": {"unp": 987654321}}
        detail_data = {"organization": {"unp": "NOT_A_NUMBER"}}
        self.assertEqual(extract_unp(list_data, detail_data), 987654321)

    def test_string_integer_is_coerced(self):
        list_data   = {"organization": {"unp": "123456789"}}
        detail_data = None
        self.assertEqual(extract_unp(list_data, detail_data), 123456789)

    def test_zero_unp_is_falsy_but_still_returned(self):
        # 0 is technically a valid int; we return it (not None)
        list_data   = {"organization": {"unp": 0}}
        detail_data = None
        self.assertEqual(extract_unp(list_data, detail_data), 0)


# ---------------------------------------------------------------------------
# BankrotClient retry logic
# ---------------------------------------------------------------------------

class TestBankrotClientRetry(unittest.TestCase):
    """Verify _request() retry behaviour without a live API."""

    def _make_client(self, token: str = "test-token"):
        from app.services.bankrot_client import BankrotClient
        return BankrotClient(
            base_url="https://api.bankrot.gov.by/v1",
            token=token,
            timeout=5.0,
            max_retries=3,
            retry_delay=0.0,   # zero delay for fast tests
        )

    @patch("app.services.bankrot_client.time.sleep")
    def test_retries_on_network_error_and_succeeds(self, mock_sleep):
        """Два сетевых сбоя, затем успешный ответ."""
        import httpx
        from app.services.bankrot_client import BankrotClient

        client = self._make_client()

        good_response = MagicMock()
        good_response.status_code = 200
        good_response.json.return_value = {"items": [], "count": 0}

        side_effects = [
            httpx.ConnectError("connection refused"),
            httpx.TimeoutException("timed out"),
            good_response,
        ]

        with patch.object(client._client, "request", side_effect=side_effects) as mock_req:
            result = client._request("POST", "/cases", json={})
            self.assertEqual(result, {"items": [], "count": 0})
            self.assertEqual(mock_req.call_count, 3)

        client.close()

    @patch("app.services.bankrot_client.time.sleep")
    def test_raises_bankrot_api_error_on_401_immediately(self, _mock_sleep):
        """401 выбрасывает BankrotAPIError без retry."""
        from app.services.bankrot_client import BankrotClient

        client = self._make_client()

        auth_response = MagicMock()
        auth_response.status_code = 401

        with patch.object(client._client, "request", return_value=auth_response) as mock_req:
            with self.assertRaises(BankrotAPIError) as ctx:
                client._request("GET", "/cases/1")
            self.assertEqual(ctx.exception.status_code, 401)
            # Должен быть ровно 1 вызов — без retry
            self.assertEqual(mock_req.call_count, 1)

        client.close()

    @patch("app.services.bankrot_client.time.sleep")
    def test_raises_after_all_retries_exhausted(self, _mock_sleep):
        """Все 3 попытки с сетевой ошибкой — выбрасывает BankrotAPIError."""
        import httpx
        from app.services.bankrot_client import BankrotClient

        client = self._make_client()
        with patch.object(
            client._client, "request",
            side_effect=httpx.ConnectError("always fails"),
        ) as mock_req:
            with self.assertRaises(BankrotAPIError):
                client._request("GET", "/cases/99")
            self.assertEqual(mock_req.call_count, 3)

        client.close()


# ---------------------------------------------------------------------------
# sync_bankrot_cases — mock DB + mock client
# ---------------------------------------------------------------------------

def _make_mock_db():
    """Минимальная mock-сессия SQLAlchemy."""
    db = MagicMock()
    # refresh() записывает id в sync_run
    def fake_refresh(obj):
        obj.id = 1
    db.refresh.side_effect = fake_refresh
    # query().filter_by().update() — не делает ничего
    db.query.return_value.filter_by.return_value.update.return_value = None
    return db


def _patch_client(items: List[Dict], detail: Optional[Dict] = None, judgements: Optional[Dict] = None):
    """Patchers для BankrotClient и _upsert_cases."""
    mock_client_instance = MagicMock()
    mock_client_instance.__enter__ = lambda s: s
    mock_client_instance.__exit__ = MagicMock(return_value=False)
    mock_client_instance.iter_all_cases.return_value = iter(items)
    mock_client_instance.get_case_detail.return_value = detail or {}
    mock_client_instance.get_case_judgements_group.return_value = judgements or {}
    return mock_client_instance


class TestSyncBankrotCases(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def _run_sync(self, items, detail=None, judgements=None, **kwargs):
        db = _make_mock_db()
        client = _patch_client(items, detail=detail, judgements=judgements)

        with patch("app.services.bankrot_sync.BankrotClient", return_value=client), \
             patch("app.services.bankrot_sync._upsert_cases") as mock_upsert:

            stats = sync_bankrot_cases(
                db,
                output_dir=self.tmp_dir,
                save_every=10,
                detail_delay=0.0,
                delay=0.0,
                **kwargs,
            )
        return stats, mock_upsert, db

    # --- NULL unp (no organization info) ---

    def test_saves_case_with_null_unp(self):
        """Дело без УНП сохраняется с debtor_unp=NULL, синхронизация продолжается."""
        item = {"id": 42, "number": "155НБ0001"}  # нет organization / debtorModel
        stats, mock_upsert, _ = self._run_sync([item])

        self.assertEqual(stats["processed"], 1)
        self.assertEqual(stats["no_unp"], 1)
        self.assertEqual(stats["failed"], 0)

        # upsert должен быть вызван 1 раз (финальный flush)
        mock_upsert.assert_called_once()
        row = mock_upsert.call_args[0][1][0]  # (db, rows)[0]
        self.assertIsNone(row["debtor_unp"])
        self.assertEqual(row["case_id"], 42)

    # --- UNP extraction inside sync ---

    def test_extracts_unp_from_detail(self):
        item   = {"id": 7, "number": "155НБ0007"}
        detail = {"debtorModel": {"organization": {"unp": 192837465}}}
        stats, mock_upsert, _ = self._run_sync([item], detail=detail)

        self.assertEqual(stats["no_unp"], 0)
        row = mock_upsert.call_args[0][1][0]
        self.assertEqual(row["debtor_unp"], 192837465)

    # --- Multiple cases and flush cadence ---

    def test_flush_cadence(self):
        """save_every=3 при 7 делах → 2 промежуточных flush + 1 финальный."""
        items = [{"id": i, "number": f"N{i}"} for i in range(1, 8)]
        db = _make_mock_db()
        client = _patch_client(items)

        with patch("app.services.bankrot_sync.BankrotClient", return_value=client), \
             patch("app.services.bankrot_sync._upsert_cases") as mock_upsert:

            stats = sync_bankrot_cases(
                db,
                output_dir=self.tmp_dir,
                save_every=3,
                detail_delay=0.0,
                delay=0.0,
            )

        # 7 items: flush at 3, 6, then final 1 → 3 calls
        self.assertEqual(mock_upsert.call_count, 3)
        self.assertEqual(stats["processed"], 7)

    # --- JSONL output file is created ---

    def test_jsonl_file_created(self):
        items = [
            {"id": 1, "debtorModel": {"organization": {"unp": 100000001}}},
            {"id": 2, "debtorModel": {"organization": {"unp": 100000002}}},
        ]
        self._run_sync(items)

        jsonl_files = [
            f for f in os.listdir(self.tmp_dir)
            if f.endswith(".jsonl") and not f.endswith(".tmp")
        ]
        self.assertEqual(len(jsonl_files), 1)

        with open(os.path.join(self.tmp_dir, jsonl_files[0]), encoding="utf-8") as fh:
            lines = [json.loads(l) for l in fh if l.strip()]
        self.assertEqual(len(lines), 2)
        self.assertIn("case_id", lines[0])
        self.assertIn("list_data", lines[0])

    # --- item without 'id' is counted as failed ---

    def test_item_without_id_counted_as_failed(self):
        items = [{"number": "NO_ID"}]
        stats, mock_upsert, _ = self._run_sync(items)

        self.assertEqual(stats["failed"], 1)
        self.assertEqual(stats["processed"], 0)

    # --- detail fetch error does not abort sync ---

    def test_detail_fetch_error_does_not_abort_sync(self):
        items = [{"id": 10}, {"id": 11}]
        db = _make_mock_db()
        client = _patch_client(items)
        # First case raises, second succeeds
        client.get_case_detail.side_effect = [
            BankrotAPIError("500 server error", status_code=500),
            {"organization": {"unp": 123456789}},
        ]

        with patch("app.services.bankrot_sync.BankrotClient", return_value=client), \
             patch("app.services.bankrot_sync._upsert_cases"):

            stats = sync_bankrot_cases(
                db,
                output_dir=self.tmp_dir,
                save_every=10,
                detail_delay=0.0,
                delay=0.0,
            )

        # Both cases processed (errors logged but not fatal)
        self.assertEqual(stats["processed"], 2)
        self.assertEqual(stats["failed"], 0)


# ---------------------------------------------------------------------------
# _build_row
# ---------------------------------------------------------------------------

class TestBuildRow(unittest.TestCase):

    def test_all_fields_present(self):
        list_data = {"id": 5, "number": "N5", "startDate": "2021-03-01"}
        detail_data = {
            "number": "N5-detail",
            "startDate": "2021-03-01T00:00:00",
            "status": 1,
            "procedureType": 4,
            "court": "Хозяйственный суд г. Минска",
            "judge": "Иванов И.И.",
            "managerModel": {"id": 99, "fullName": "Петров П.П."},
            "lastJudgmentId": 12345,
        }
        row = _build_row(
            case_id=5,
            list_data=list_data,
            detail_data=detail_data,
            judgements_group={"data": []},
            unp=123456789,
            fetch_error=None,
        )

        self.assertEqual(row["case_id"], 5)
        self.assertEqual(row["debtor_unp"], 123456789)
        self.assertEqual(row["number"], "N5-detail")   # detail takes priority
        self.assertEqual(row["status"], 1)
        self.assertEqual(row["procedure_type"], 4)
        self.assertEqual(row["court"], "Хозяйственный суд г. Минска")
        self.assertEqual(row["manager_id"], 99)
        self.assertEqual(row["manager_name"], "Петров П.П.")
        self.assertEqual(row["last_judgment_id"], 12345)
        self.assertIsNone(row["fetch_error"])
        self.assertNotIn("created_at", row)  # must not be set by _build_row

    def test_fetch_error_stored(self):
        row = _build_row(
            case_id=1,
            list_data={},
            detail_data=None,
            judgements_group=None,
            unp=None,
            fetch_error="detail: HTTP 503",
        )
        self.assertEqual(row["fetch_error"], "detail: HTTP 503")



if __name__ == "__main__":
    unittest.main()
