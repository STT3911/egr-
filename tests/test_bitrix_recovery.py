import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.bitrix.bitrix_client import BitrixAPIError
from app.bitrix.egr_client import EGRCompanyInfo
from app.bitrix.recovery import RecoveryClient, discover, recover, save_state
from app.bitrix.requisite_service import RequisiteService


def state():
    return {"since": "2026-09-15T12:00:00+03:00", "until": "2026-09-21T12:00:00+03:00",
            "company_ids": [], "next_index": 0, "preview_index": 0,
            "discovery": {k: {"last_id": 0, "complete": False} for k in ("DATE_CREATE", "DATE_MODIFY")}}


def test_discovery_unions_created_modified_and_keysets_all_pages():
    s = state()
    client = Mock(call=AsyncMock(side_effect=[[{"ID": "1"}, {"ID": "2"}], [], [{"ID": "2"}, {"ID": "3"}], []]))
    checkpoints = []
    asyncio.run(discover(client, s, lambda value: checkpoints.append(deepcopy(value))))
    assert s["company_ids"] == [1, 2, 3]
    assert client.call.await_args_list[1].args[1]["filter"][">ID"] == 2
    assert client.call.await_args_list[2].args[1]["filter"][">=DATE_MODIFY"] == s["since"]
    assert len(checkpoints) == 4 and all(v["complete"] for v in s["discovery"].values())


def test_failure_does_not_advance_replay_checkpoint():
    s = state()
    s["company_ids"] = [1, 2]
    for v in s["discovery"].values():
        v["complete"] = True
    service = Mock(process_company_update=AsyncMock(side_effect=[{"status": "filled"}, BitrixAPIError("expired_token")]))
    with pytest.raises(BitrixAPIError):
        asyncio.run(recover(service, s, lambda v: None, apply=True))
    assert s["next_index"] == 1
    service.process_company_update = AsyncMock(return_value={"status": "filled"})
    asyncio.run(recover(service, s, lambda v: None, apply=True))
    service.process_company_update.assert_awaited_once_with(2, recovery_mode=True, dry_run=False)


def test_dry_run_never_advances_apply_position():
    s = state()
    s["company_ids"] = [1]
    for v in s["discovery"].values():
        v["complete"] = True
    service = Mock(process_company_update=AsyncMock(return_value={"status": "would_fill"}))
    asyncio.run(recover(service, s, lambda v: None))
    assert s["preview_index"] == 1 and s["next_index"] == 0


@pytest.mark.parametrize("method", ["im.notify", "crm.company.update", "crm.requisite.delete", "crm.requisite.bankdetail.add"])
def test_recovery_rejects_messages_company_writes_and_deletions(method):
    client = RecoveryClient(Mock(), apply=True)
    with pytest.raises(BitrixAPIError, match="forbidden"):
        asyncio.run(client.call(method, {}))


def test_preview_rejects_requisite_write():
    with pytest.raises(BitrixAPIError, match="forbidden"):
        asyncio.run(RecoveryClient(Mock()).call("crm.requisite.add", {}))


def test_wrong_oauth_app_stops_recovery_before_writes():
    client = RecoveryClient(Mock())
    client._load_settings = AsyncMock(return_value=SimpleNamespace(bitrix_client_id="local.expected", bitrix_client_secret="test"))
    client.call = AsyncMock(return_value={"CODE": "local.other"})
    with pytest.raises(BitrixAPIError, match="different app"):
        asyncio.run(client.verify_application())
    client.call.assert_awaited_once_with("app.info")


def test_missing_only_preserves_manual_fields_address_and_bank_details():
    bitrix = SimpleNamespace(get_address_type_id=AsyncMock(return_value=6),
        call=AsyncMock(side_effect=[[{"ADDRESS_1": "Manual address", "POSTAL_CODE": ""}], True]),
        update_requisite=AsyncMock(return_value=True), create_requisite=AsyncMock())
    service = RequisiteService(bitrix, None)
    result = asyncio.run(service._recover_requisite(1, "193879557", SimpleNamespace(requisite_preset_id=2),
        {"ID": "9", "RQ_COMPANY_NAME": "Manual name", "RQ_DIRECTOR": ""},
        {"RQ_COMPANY_NAME": "EGR name", "RQ_DIRECTOR": "Director"},
        {"ADDRESS_1": "EGR address", "POSTAL_CODE": "220103"}, dry_run=False))
    bitrix.update_requisite.assert_not_called()
    assert bitrix.call.await_args_list[-1].args == ("crm.requisite.update", {"id": 9, "fields": {"RQ_DIRECTOR": "Director"}})
    assert result["status"] == "filled" and result["address_fields"] == []
    bitrix.create_requisite.assert_not_called()
    assert [c.args[0] for c in bitrix.call.await_args_list] == ["crm.address.list", "crm.requisite.update"]


def test_dry_run_creates_nothing_and_reports_only_field_names():
    bitrix = SimpleNamespace(get_address_type_id=AsyncMock(return_value=6), create_requisite=AsyncMock(), call=AsyncMock())
    service = RequisiteService(bitrix, None)
    result = asyncio.run(service._recover_requisite(1, "193879557", SimpleNamespace(requisite_preset_id=2), None,
        {"RQ_COMPANY_NAME": "Name"}, {"ADDRESS_1": "Address"}, dry_run=True))
    assert result["status"] == "would_create"
    assert "Name" not in str(result) and "Address" not in str(result)
    bitrix.create_requisite.assert_not_called()
    bitrix.call.assert_not_called()


def test_partial_creation_address_failure_is_recoverable():
    bitrix = SimpleNamespace(get_address_type_id=AsyncMock(return_value=6),
        create_requisite=AsyncMock(return_value=12), call=AsyncMock(side_effect=BitrixAPIError("timeout")),
        update_requisite=AsyncMock(return_value=True))
    service = RequisiteService(bitrix, None)
    with pytest.raises(BitrixAPIError):
        asyncio.run(service._recover_requisite(1, "193879557", SimpleNamespace(requisite_preset_id=2), None,
            {"NAME": "Name"}, {"ADDRESS_1": "Address"}, dry_run=False))
    bitrix.call = AsyncMock(side_effect=[[], True])
    result = asyncio.run(service._recover_requisite(1, "193879557", SimpleNamespace(requisite_preset_id=2),
        {"ID": "12", "NAME": "Name"}, {"NAME": "Name"}, {"ADDRESS_1": "Address"}, dry_run=False))
    assert result["status"] == "filled"
    assert bitrix.create_requisite.await_count == 1
    assert bitrix.call.await_args_list[-1].args[0] == "crm.address.add"


def test_atomic_checkpoint_roundtrip(tmp_path):
    import json
    path = tmp_path / "state.json"
    save_state(path, state())
    assert json.loads(path.read_text()) == state()
    assert not path.with_name("state.json.partial").exists()


def test_recovery_normalizes_existing_unp_and_never_renames_company():
    cfg = SimpleNamespace(unp_field_code="UF_UNP", requisite_preset_id=2)
    bitrix = SimpleNamespace(_load_settings=AsyncMock(return_value=cfg),
        call=AsyncMock(side_effect=[{"ID": "1", "TITLE": "Manual", "UF_UNP": "193879557"},
                                   [{"ID": "12", "RQ_INN": "193 879 557", "NAME": "Manual"}], True]),
        update_requisite=AsyncMock(return_value=True))
    egr = SimpleNamespace(get_company_info=AsyncMock(return_value=EGRCompanyInfo(
        full_name="EGR name", short_name="EGR", is_ip=False, is_empty=False)))
    result = asyncio.run(RequisiteService(bitrix, egr).process_company_update(1, recovery_mode=True))
    assert result["status"] == "filled"
    fields = bitrix.call.await_args_list[-1].args[1]["fields"]
    assert "NAME" not in fields and "RQ_INN" not in fields
    bitrix.update_requisite.assert_not_called()
    assert all(c.args[0] != "crm.company.update" for c in bitrix.call.await_args_list)
