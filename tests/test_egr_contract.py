import importlib.util
from datetime import date
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import BigInteger

from app.crud.company import CompanyCRUD
from app.database.models import CompanyAddressHistory, CompanyNameHistory, CompanyEvent
from app.services.egr_contract import egr_date, map_event
from app.services.mapper_service import CompanyMapper


@pytest.mark.parametrize("raw,expected", [
    ("2026-08-24T21:00:00.000+00:00", date(2026, 8, 25)),
    ("2026-08-25T00:00:00+03:00", date(2026, 8, 25)),
    ("2026-08-25", date(2026, 8, 25)), ("25.08.2026", date(2026, 8, 25)),
    (None, None), ("garbage", None),
])
def test_dates_use_minsk_without_moving_date_only_values(raw, expected):
    assert egr_date(raw) == expected


@pytest.mark.parametrize("status,code", [("Ликвидация", 3), ("В процессе ликвидации", 3),
    ("Исключен", 2), ("Исключен из ЕГР", 2), ("Банкротство", 4), ("Прекращение деятельности", None)])
def test_mobile_status_mapping_matches_official_codes(status, code):
    result = CompanyMapper().map_to_db_structure(193879557, {"common_info": {"state": status}})
    assert result["company"]["current_status_code"] == code


def test_actual_address_contract_not_residential_heuristic():
    result = CompanyMapper().map_to_db_structure(193879557, {"base_info": {"ngrn": 193879557},
        "addresses": [{"dfrom": "2026-08-24T21:00:00Z", "vnp": "Минск", "vulitsa": "Кнорина",
        "vdom": "55", "vpom": "2-1", "nsi00227": {"vntpomk": "пом."},
        "nsi00234": {"vnvpom": "Нежилое помещение"}, "vadrprim": "комнаты 13,14,15",
        "vsite": "https://example.test", "vfax": "1234567"}]})
    addr = result["addresses"][0]
    assert "пом. 2-1" in addr["full_address"] and "оф." not in addr["full_address"]
    assert addr["valid_from"] == date(2026, 8, 25)
    assert addr["_legacy_valid_from"] == date(2026, 8, 24)
    assert result["contacts"][0]["website"] == "https://example.test"
    assert result["contacts"][0]["fax"] == "1234567"


def test_document_uppercase_fields_and_null_references():
    result = CompanyMapper().map_to_db_structure(193879557, {"base_info": {"NGRN": 193879557,
        "NSI00219": None, "NSI00211": {"nkvob": 2}},
        "names": [{"VFIO": "Фамилия", "VFIOB": "Прозвішча"}],
        "addresses": [{"VNP": "Минск", "NSI00201": None, "NSI00239": None}]})
    assert result["names"][0]["full_name_by"] == "Прозвішча"
    assert result["addresses"][0]["full_address"] == "Минск"


def test_date_and_format_correction_reuses_existing_address_row():
    row = CompanyAddressHistory(full_address="Old formatting", valid_from=date(2026, 8, 24), valid_to=None)
    db = Mock()
    db.query.return_value.filter.return_value.all.return_value = [row]
    db.query.return_value.filter.return_value.first.return_value = None
    added = CompanyCRUD(db)._save_addresses_history(SimpleNamespace(id=1, unp=193879557), [{
        "full_address": "New formatting", "valid_from": date(2026, 8, 25), "valid_to": None,
        "_legacy_valid_from": date(2026, 8, 24)}], authoritative=True)
    assert added == [] and row.valid_from == date(2026, 8, 25)
    db.add.assert_not_called()
    db.delete.assert_not_called()


def test_date_correction_reuses_name_row_and_ambiguous_merge_stops():
    row = CompanyNameHistory(full_name_ru="Name", valid_from=date(2026, 8, 24), valid_to=None)
    db = Mock()
    db.query.return_value.filter.return_value.all.return_value = [row]
    payload = {"full_name_ru": "Name", "valid_from": date(2026, 8, 25), "valid_to": None,
               "_legacy_valid_from": date(2026, 8, 24)}
    assert CompanyCRUD(db)._save_names_history(SimpleNamespace(id=1), [payload]) == []
    assert row.valid_from == date(2026, 8, 25)
    db.add.assert_not_called()
    db.query.return_value.filter.return_value.all.return_value = [row,
        CompanyNameHistory(full_name_ru="Name", valid_from=date(2026, 8, 24), valid_to=None)]
    with pytest.raises(ValueError, match="Ambiguous"):
        CompanyCRUD(db)._save_names_history(SimpleNamespace(id=1), [payload])


def test_events_keep_int64_id_cancellation_and_suspension_dates():
    event = map_event({"ngr04004": 18241482500, "dfrom": "2026-08-24T21:00:00Z",
        "dto": "2026-09-01", "dsrok2": "2026-10-01", "nsi00223": {"nkop": 41700, "vnop": "Приостановление"}})
    assert event["event_record_id"] == 18241482500
    assert event["event_date"] == date(2026, 8, 25)
    assert event["cancel_date"] == date(2026, 9, 1)
    assert event["suspension_end_date"] == date(2026, 10, 1)
    assert isinstance(CompanyEvent.__table__.c.event_record_id.type, BigInteger)


def test_migration_generates_postgres_bigint_and_unique_index_without_data_deletion():
    path = Path(__file__).resolve().parents[1] / "migrations/versions/egrapi2_contract_history.py"
    spec = importlib.util.spec_from_file_location("egr_migration_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    module.op = Operations(context)
    module.upgrade()
    sql = output.getvalue()
    assert "ALTER COLUMN event_record_id TYPE BIGINT" in sql
    assert "CREATE UNIQUE INDEX uq_egr_event_source" in sql and "WHERE event_record_id IS NOT NULL" in sql
    assert "CREATE TABLE egr_ip_to_jur" in sql
    assert "DELETE " not in sql and "DROP " not in sql
