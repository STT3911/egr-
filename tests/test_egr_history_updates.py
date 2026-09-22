from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock
import random

import pytest

from app.crud.company import CompanyCRUD
from app.database.models import CompanyAddressHistory, CompanyNameHistory, CompanyVEDHistory, CompanyPlaceLocation
from app.services.mapper_service import CompanyMapper
from app.services.egr_contract import period_fields


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


def address_regression_fixture():
    # Shape of the 291265296 production failure: two distinct periods start
    # on the same day; the former active row now closes and changes formatting.
    periods = [
        ("Коммерческая 7", "2013-12-19", "2015-01-11"),
        ("Островского 12", "2015-01-11", "2016-05-01"),
        ("Красногвардейская 129", "2016-05-01", "2020-02-19"),
        ("17 Сентября 12, оф. 52", "2020-02-19", "2024-02-13"),
        ("17 Сентября 12, оф. 52", "2024-02-13", "2024-02-13"),
        ("17 Сентября 12, оф. 52", "2024-02-13", None),
    ]
    existing = [CompanyAddressHistory(id=str(i), full_address=name,
                valid_from=date.fromisoformat(start), valid_to=date.fromisoformat(end) if end else None)
                for i, (name, start, end) in enumerate(periods)]
    periods[3] = ("17 Сентября 12, пом. 52", "2020-02-19", "2024-02-13")
    periods[5] = ("Ленинский, 17 Сентября 12, оф. 52", "2024-02-13", "2026-08-24")
    periods.append(("Ленинский, Кижеватова 12, пом. 10", "2026-08-24", None))
    incoming = [{"full_address": name, **period_fields({
        "dfrom": start + "T21:00:00Z", "dto": end + "T21:00:00Z" if end else None})}
        for name, start, end in periods]
    return existing, incoming


@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize("partially_corrected", [False, True])
def test_same_day_periods_are_repaired_one_to_one_and_repeat_is_idempotent(seed, partially_corrected):
    rows, incoming = address_regression_fixture()
    original = list(rows)
    if partially_corrected:
        CompanyCRUD._update_history_entry(rows[4], {k: v for k, v in incoming[4].items() if not k.startswith("_")})
    random.Random(seed).shuffle(rows)
    random.Random(seed + 1).shuffle(incoming)
    pl = CompanyPlaceLocation(address="old cached address")
    db = history_db(CompanyAddressHistory, rows, pl)
    db.add.side_effect = rows.append
    crud = CompanyCRUD(db)
    company = SimpleNamespace(id=1, unp=291265296)
    added = crud._save_addresses_history(company, incoming, authoritative=True)
    assert len(added) == 1 and len(rows) == 7
    assert original[4].valid_from == original[4].valid_to == date(2024, 2, 14)
    assert original[5].valid_from == date(2024, 2, 14)
    assert original[5].valid_to == date(2026, 8, 25)
    assert original[5].full_address.startswith("Ленинский")
    assert original[3].full_address.endswith("пом. 52")
    assert pl.address is None
    snapshot = [(id(r), r.full_address, r.valid_from, r.valid_to) for r in rows]
    assert crud._save_addresses_history(company, list(reversed(incoming)), authoritative=True) == []
    assert snapshot == [(id(r), r.full_address, r.valid_from, r.valid_to) for r in rows]
    assert sum(r.valid_to is None for r in rows) == 1
    db.delete.assert_not_called()


def test_real_ambiguity_fails_before_any_address_is_mutated():
    rows, incoming = address_regression_fixture()
    # An indistinguishable extra DB row must not be merged/deleted arbitrarily.
    rows.append(CompanyAddressHistory(full_address=rows[4].full_address,
                                     valid_from=rows[4].valid_from, valid_to=rows[4].valid_to))
    before = [(r.full_address, r.valid_from, r.valid_to) for r in rows]
    db = history_db(CompanyAddressHistory, rows)
    with pytest.raises(ValueError, match="Ambiguous EGR address periods"):
        CompanyCRUD(db)._save_addresses_history(SimpleNamespace(id=1), incoming)
    assert before == [(r.full_address, r.valid_from, r.valid_to) for r in rows]
    db.add.assert_not_called()
    db.delete.assert_not_called()


def test_identical_source_addresses_do_not_create_duplicate_rows():
    db = history_db(CompanyAddressHistory, [])
    address = {"full_address": "address", "valid_from": date(2026, 1, 1), "valid_to": None}
    assert CompanyCRUD(db)._save_addresses_history(SimpleNamespace(id=1), [address, dict(address)]) == [address]
    db.add.assert_called_once()


def test_two_same_day_addresses_with_different_ends_are_not_collapsed():
    rows = []
    db = history_db(CompanyAddressHistory, rows)
    db.add.side_effect = rows.append
    crud = CompanyCRUD(db)
    company = SimpleNamespace(id=1)
    data = [{"full_address": "address", "valid_from": date(2026, 1, 1), "valid_to": end}
            for end in [date(2026, 1, 1), None]]
    assert len(crud._save_addresses_history(company, data)) == 2
    assert crud._save_addresses_history(company, data) == []
    assert len(rows) == 2
