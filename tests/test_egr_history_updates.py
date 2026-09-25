from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock
import random

import pytest

from app.crud.company import CompanyCRUD
from app.database.models import CompanyAddressHistory, CompanyNameHistory, CompanyVEDHistory, CompanyPlaceLocation, CompanyContactHistory
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


HISTORY_TYPES = [
    (CompanyNameHistory, "_save_names_history", "full_name_ru"),
    (CompanyVEDHistory, "_save_ved_history", "ved_code"),
    (CompanyContactHistory, "_save_contacts_history", "phone"),
]


@pytest.mark.parametrize("model,method,field", HISTORY_TYPES)
@pytest.mark.parametrize("seed", range(6))
def test_unique_chain_of_one_day_periods_uses_global_assignment(model, method, field, seed):
    # Production 600112236: canonical period N equals legacy period N+1.
    rows = [model(**{field: "same", "valid_from": date(2003, 6, n),
                     "valid_to": date(2003, 6, n + 1)}) for n in (3, 4)]
    original = list(rows)
    incoming = [{field: "same", **period_fields({"dfrom": f"2003-06-0{n}T21:00:00Z",
                 "dto": f"2003-06-0{n+1}T21:00:00Z"})} for n in (3, 4)]
    random.Random(seed).shuffle(rows)
    random.Random(seed + 1).shuffle(incoming)
    db = history_db(model, rows)
    save = getattr(CompanyCRUD(db), method)
    save(SimpleNamespace(id=1), incoming)
    assert [(r.valid_from, r.valid_to) for r in original] == [
        (date(2003, 6, 4), date(2003, 6, 5)), (date(2003, 6, 5), date(2003, 6, 6))]
    save(SimpleNamespace(id=1), list(reversed(incoming)))
    db.add.assert_not_called()
    db.delete.assert_not_called()


@pytest.mark.parametrize("seed", range(8))
def test_legacy_address_renderer_disambiguates_village_and_agrotown(seed):
    # Production 291210083: an earlier import kept two observations for
    # the same open period. Adding the district must not merge both rows.
    rows = [CompanyAddressHistory(full_address=value, valid_from=start, valid_to=end)
            for value, start, end in [
                ("Брестская, д. Рудники, д. 41", date(2014, 9, 17), date(2019, 1, 3)),
                ("Брестская, д. Рудники, д. 41", date(2019, 1, 3), None),
                ("Брестская, аг. Рудники, д. 41", date(2019, 1, 3), None),
            ]]
    old, retained, current = rows
    raw = {"base_info": {"ngrn": 291210083}, "addresses": [
        {"vregion": "Брестская", "vdistrict": "Пружанский", "vnp": "Рудники",
         "nsi00239": {"vntnpk": kind}, "vdom": "41", "dfrom": start, "dto": end}
        for kind, start, end in [
            ("д.", "2014-09-17T21:00:00Z", "2019-01-03T21:00:00Z"),
            ("аг.", "2019-01-03T21:00:00Z", None),
        ]]}
    incoming = CompanyMapper().map_to_db_structure(291210083, raw)["addresses"]
    assert incoming[1]["_legacy_full_address"] == current.full_address
    random.Random(seed).shuffle(rows)
    random.Random(seed + 1).shuffle(incoming)
    db = history_db(CompanyAddressHistory, rows)
    db.add.side_effect = rows.append
    save = CompanyCRUD(db)._save_addresses_history
    assert save(SimpleNamespace(id=1), incoming) == []
    assert old.valid_from == date(2014, 9, 18)
    assert old.valid_to == date(2019, 1, 4)
    assert current.valid_from == date(2019, 1, 4)
    assert "Пружанский" in current.full_address
    assert retained.full_address == "Брестская, д. Рудники, д. 41"
    assert retained.valid_from == date(2019, 1, 3) and retained.valid_to is None
    assert save(SimpleNamespace(id=1), list(reversed(incoming))) == []
    db.add.assert_not_called()
    db.delete.assert_not_called()


@pytest.mark.parametrize("model,method,field", HISTORY_TYPES)
@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("partially_corrected", [False, True])
def test_adjacent_period_date_correction_does_not_confuse_next_row(model, method, field, seed, partially_corrected):
    # Production UNP 491388269, anonymized: the corrected start of one
    # contact period is also the legacy start of the next one.
    rows = [
        model(**{field: "old", "valid_from": date(2024, 5, 21), "valid_to": None}),
        model(**{field: "same", "valid_from": date(2026, 5, 31), "valid_to": date(2026, 6, 1)}),
        model(**{field: "same", "valid_from": date(2026, 6, 1), "valid_to": None}),
    ]
    original = list(rows)
    incoming = [{field: value, **period_fields({"dfrom": start + "T21:00:00Z",
                 "dto": end + "T21:00:00Z" if end else None})}
                for value, start, end in [("same", "2026-05-31", "2026-06-01"),
                                         ("same", "2026-06-01", None),
                                         ("old", "2024-05-21", "2026-05-31")]]
    if partially_corrected:
        CompanyCRUD._update_history_entry(rows[1], {k:v for k,v in incoming[0].items() if not k.startswith("_")})
    random.Random(seed).shuffle(rows)
    random.Random(seed + 1).shuffle(incoming)
    db = history_db(model, rows)
    db.add.side_effect = rows.append
    save = getattr(CompanyCRUD(db), method)
    save(SimpleNamespace(id=1), incoming)
    assert [(r.valid_from, r.valid_to) for r in original] == [
        (date(2024, 5, 22), date(2026, 6, 1)),
        (date(2026, 6, 1), date(2026, 6, 2)),
        (date(2026, 6, 2), None),
    ]
    save(SimpleNamespace(id=1), list(reversed(incoming)))
    assert len(rows) == 3
    db.add.assert_not_called()
    db.delete.assert_not_called()
    if model is CompanyNameHistory:
        assert all(row.search_name for row in rows)


@pytest.mark.parametrize("model,method,field", HISTORY_TYPES)
def test_same_day_distinct_periods_and_source_duplicates_in_all_histories(model, method, field):
    rows = []
    db = history_db(model, rows)
    db.add.side_effect = rows.append
    save = getattr(CompanyCRUD(db), method)
    incoming = [{field:"same", "valid_from":date(2026, 6, 1), "valid_to":end}
                for end in [date(2026, 6, 1), None]]
    save(SimpleNamespace(id=1), incoming + [dict(incoming[0])])
    assert len(rows) == 2
    save(SimpleNamespace(id=1), list(reversed(incoming)))
    assert len(rows) == 2
    assert {r.valid_to for r in rows} == {None, date(2026, 6, 1)}


@pytest.mark.parametrize("model,method,field", HISTORY_TYPES)
def test_truly_ambiguous_history_is_not_merged_or_deleted(model, method, field):
    rows = [model(**{field:"same", "valid_from":date(2026, 6, 1), "valid_to":None}) for _ in range(2)]
    db = history_db(model, rows)
    incoming = [{field:"same", "valid_from":date(2026, 6, 1), "valid_to":date(2026, 6, 2)}]
    with pytest.raises(ValueError, match="Ambiguous EGR"):
        getattr(CompanyCRUD(db), method)(SimpleNamespace(id=1), incoming)
    assert all(r.valid_to is None for r in rows)
    db.add.assert_not_called()
    db.delete.assert_not_called()


def test_contact_enrichment_preserves_distinct_phones_and_nonempty_websites():
    day = date(2026, 6, 1)
    rows = [CompanyContactHistory(phone="one", valid_from=day),
            CompanyContactHistory(phone="two", website="https://old.example", valid_from=day)]
    db = history_db(CompanyContactHistory, rows)
    db.add.side_effect = rows.append
    data = [{"phone":"one", "website":"https://one.example", "valid_from":day, "valid_to":None},
            {"phone":"two", "website":"https://new.example", "valid_from":day, "valid_to":None}]
    crud = CompanyCRUD(db)
    crud._save_contacts_history(SimpleNamespace(id=1), data)
    assert len(rows) == 3
    assert rows[0].website == "https://one.example"
    assert rows[1].website == "https://old.example"
    crud._save_contacts_history(SimpleNamespace(id=1), data)
    assert len(rows) == 3


def test_unique_assignment_matches_exhaustive_small_graphs():
    from itertools import product, permutations
    # All nonempty candidate sets for three records and three DB rows.
    options = [[j for j in range(3) if mask & (1 << j)] for mask in range(1, 8)]
    for graph in product(options, repeat=3):
        candidates = dict(enumerate(graph))
        solutions = [dict(enumerate(p)) for p in permutations(range(3))
                     if all(p[i] in graph[i] for i in range(3))]
        actual = CompanyCRUD._unique_period_assignment(candidates)
        if len(solutions) == 1:
            assert actual == solutions[0]
        elif solutions:
            assert all(all(solution[i] == j for solution in solutions) for i, j in actual.items())
