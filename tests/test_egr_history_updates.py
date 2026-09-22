from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

from app.crud.company import CompanyCRUD
from app.database.models import CompanyAddressHistory, CompanyNameHistory, CompanyVEDHistory, CompanyPlaceLocation
from app.services.mapper_service import CompanyMapper


def history_db(model, rows, location=None):
    db = Mock()
    def query(queried):
        result = Mock()
        if queried is model:
            result.filter.return_value.all.return_value = rows
        elif queried is CompanyPlaceLocation:
            result.filter.return_value.first.return_value = location
        else:
            raise AssertionError(queried)
        return result
    db.query.side_effect = query
    return db


def test_address_change_closes_old_period_retains_history_and_invalidates_mobile():
    old = CompanyAddressHistory(full_address="Макаенка 12Г", valid_from=date(2025, 6, 12), valid_to=None)
    pl = CompanyPlaceLocation(address="Макаенка 12Г", raw_json="Макаенка 12Г", lat=53, lon=27)
    db = history_db(CompanyAddressHistory, [old], pl)
    addresses = [
        {"full_address": "Макаенка 12Г", "valid_from": date(2025, 6, 12), "valid_to": date(2026, 8, 25)},
        {"full_address": "Кнорина 55", "valid_from": date(2026, 8, 25), "valid_to": None},
    ]
    result = CompanyCRUD(db)._save_addresses_history(SimpleNamespace(id=1, unp=193879557), addresses, authoritative=True)
    assert old.valid_to == date(2026, 8, 25)
    assert result == [addresses[1]]
    assert pl.address is None and pl.lat is None and pl.lon is None
    assert pl.raw_json == "Макаенка 12Г"
    db.delete.assert_not_called()


def test_unchanged_address_does_not_invalidate_mobile():
    old = CompanyAddressHistory(full_address="Кнорина 55", valid_from=date(2026, 8, 25), valid_to=None)
    pl = CompanyPlaceLocation(address="Минск, Кнорина 55")
    db = history_db(CompanyAddressHistory, [old], pl)
    data = [{"full_address": old.full_address, "valid_from": old.valid_from, "valid_to": None}]
    assert CompanyCRUD(db)._save_addresses_history(SimpleNamespace(id=1, unp=193879557), data, authoritative=True) == []
    assert pl.address == "Минск, Кнорина 55"


def test_format_enrichment_updates_period_without_duplicate():
    old = CompanyAddressHistory(full_address="Кнорина 55", valid_from=date(2026, 8, 25), valid_to=None)
    db = history_db(CompanyAddressHistory, [old])
    data = [{"full_address": "Кнорина 55, комнаты 13,14,15", "valid_from": old.valid_from, "valid_to": None}]
    assert CompanyCRUD(db)._save_addresses_history(SimpleNamespace(id=1, unp=193879557), data) == []
    assert old.full_address.endswith("комнаты 13,14,15")
    db.add.assert_not_called()


def test_historical_address_addition_does_not_invalidate_current_mobile():
    old = CompanyAddressHistory(full_address="Кнорина 55", valid_from=date(2026, 8, 25), valid_to=None)
    pl = CompanyPlaceLocation(address="Минск, Кнорина 55")
    db = history_db(CompanyAddressHistory, [old], pl)
    data = [{"full_address": "Первый адрес", "valid_from": date(2020, 1, 1), "valid_to": date(2021, 1, 1)},
            {"full_address": old.full_address, "valid_from": old.valid_from, "valid_to": None}]
    CompanyCRUD(db)._save_addresses_history(SimpleNamespace(id=1, unp=193879557), data, authoritative=True)
    assert pl.address == "Минск, Кнорина 55"


def test_old_snapshot_cannot_reopen_closed_period():
    row = CompanyAddressHistory(full_address="old", valid_from=date(2020, 1, 1), valid_to=date(2021, 1, 1))
    CompanyCRUD._update_history_entry(row, {"valid_to": None})
    assert row.valid_to == date(2021, 1, 1)


def test_names_and_ved_close_existing_periods():
    for model, method, key, value in [(CompanyNameHistory, "_save_names_history", "full_name_ru", "Название"),
                                    (CompanyVEDHistory, "_save_ved_history", "ved_code", "62010")]:
        row = model(**{key: value, "valid_from": date(2020, 1, 1)})
        db = history_db(model, [row])
        payload = {key: value, "valid_from": row.valid_from, "valid_to": date(2026, 8, 25)}
        assert getattr(CompanyCRUD(db), method)(SimpleNamespace(id=1), [payload]) == []
        assert row.valid_to == date(2026, 8, 25)
        db.add.assert_not_called()


def test_mapper_preserves_building_and_address_remarks():
    payload = {"base_info": {"ngrn": 193879557}, "addresses": [{
        "vnp": "Минск", "vulitsa": "Кнорина", "vdom": "55", "vkorp": "А", "vpom": "2-1",
        "vadrprim": "комнаты 13,14,15", "nsi00234": {"vnvpom": "нежилое помещение"},
    }]}
    address = CompanyMapper().map_to_db_structure(193879557, payload)["addresses"][0]["full_address"]
    assert "корп. А" in address and "комнаты 13,14,15" in address and "2-1" in address
