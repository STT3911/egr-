from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.crud.company import CompanyCRUD
from app.database.models import Company, CompanyNameHistory, CompanyPlaceLocation
from app.schemas.company import CompanyProfileResponse
from app.services.company_address_presentation import address_region, profile_addresses


@pytest.mark.parametrize("address, expected", [
    ("Гомельская обл., Терешковичский с/с, аг. Терешковичи", "Гомельская"),
    ("Республика Беларусь, 247005, Гомельская область, Гомельский район", "Гомельская"),
    ("Витебская, г. Витебск, пр-т Строителей, д. 6", "Витебская"),
    ("Могилёвская область, г. Бобруйск", "Могилевская"),
    ("г. Минск, ул. Кнорина, д. 55", "г. Минск"),
    ("Республика Беларусь, 220103, г.Минск, ул. Кнорина", "г. Минск"),
    ("Минская область, Минский район, д. Пятевщина", "Минская"),
    ("г. Минск, ул. Минская, д. 1", "г. Минск"),
    ("г. Гомель, ул. Минская, д. 1", None),
    ("аг. Терешковичи", None),
    ("Минский район, д. Пятевщина", None),
    (None, None),
])
def test_region_uses_only_explicit_address_evidence(address, expected):
    assert address_region(address) == expected


def test_grp_address_without_egr_history_has_source_and_no_invented_dates():
    place = CompanyPlaceLocation(
        unp=400047301, address="Гомельская обл., Терешковичский с/с, аг. Терешковичи",
        raw_json={"source": "grp"}, fetched_at=date(2026, 11, 20),
    )
    rows = profile_addresses([], place)
    assert rows == [{
        "full_address": place.address,
        "postal_code": None,
        "region": "Гомельская",
        "district": None,
        "valid_from": None,
        "valid_to": None,
        "source": "grp",
    }]


def test_location_postal_code_district_and_source():
    place = SimpleNamespace(
        address="Республика Беларусь, 247005, Гомельская область, Гомельский район, аг. Терешковичи",
        raw_json={"source": "gias"},
    )
    row = profile_addresses([], place)[0]
    assert row["postal_code"] == 247005
    assert row["district"] == "Гомельский"
    assert row["source"] == "gias"


def test_existing_egr_history_wins_over_location_and_is_not_mutated():
    old = SimpleNamespace(
        full_address="г. Минск, ул. Макаенка, д. 12Г", postal_code=220114,
        region=None, district="Первомайский", valid_from=date(2025, 6, 13),
        valid_to=date(2026, 8, 25),
    )
    current = SimpleNamespace(**{**vars(old), "full_address": "г. Минск, ул. Кнорина, д. 55",
                                "valid_from": date(2026, 8, 25), "valid_to": None})
    place = SimpleNamespace(address="устаревший адрес ГРП", raw_json={"source": "grp"})
    rows = profile_addresses([old, current], place)
    assert len(rows) == 2
    assert rows[0]["valid_to"] == "2026-08-25"
    assert rows[1]["valid_from"] == "2026-08-25"
    assert rows[1]["valid_to"] is None
    assert all(row["source"] == "egr" and row["region"] == "г. Минск" for row in rows)
    assert old.region is None and current.region is None


def test_explicit_stored_region_has_priority_over_derived_region():
    row = SimpleNamespace(
        full_address="г. Минск", postal_code=None, region="Источник: Минск",
        district=None, valid_from=None, valid_to=None,
    )
    assert profile_addresses([row])[0]["region"] == "Источник: Минск"


@pytest.mark.parametrize("place", [None, SimpleNamespace(address=None), SimpleNamespace(address="  ")])
def test_missing_addresses_stay_empty(place):
    assert profile_addresses([], place) == []


def test_unknown_location_source_is_not_reported_as_grp():
    assert profile_addresses([], SimpleNamespace(address="аг. Терешковичи", raw_json=None))[0]["source"] is None


def test_mobile_location_is_egr_source():
    place = SimpleNamespace(address="г. Минск", raw_json={"vpadres": "г. Минск"})
    assert profile_addresses([], place)[0]["source"] == "egr"


def test_unrecognized_source_is_not_mislabeled_as_egr():
    place = SimpleNamespace(address="г. Минск", raw_json={"source": "manual"})
    assert profile_addresses([], place)[0]["source"] is None


def test_profile_endpoint_ignores_old_cache_and_preserves_address_source():
    import asyncio
    from unittest.mock import patch
    from app.api.v1.endpoints import companies

    payload = {
        "unp": 400047301,
        "addresses": profile_addresses([], SimpleNamespace(
            address="Гомельская обл., аг. Терешковичи", raw_json={"source": "grp"},
        )),
    }
    redis = Mock()
    redis.get.return_value = None
    with patch.object(companies, "AggregatorService") as aggregator, \
            patch.object(companies, "CompanyCRUD") as crud:
        aggregator.return_value.redis = redis
        crud.return_value.get_full_dossier.return_value = payload
        response = asyncio.run(companies.get_company_profile(
            identifier="400047301", force_refresh=False, use_mobile_api=None,
            db_only=False, db=Mock(), api_key="test",
        ))
    redis.get.assert_called_once_with("company_profile_v11:400047301")
    assert redis.setex.call_args.args[0] == "company_profile_v11:400047301"
    assert response.addresses[0].source == "grp"
    assert response.addresses[0].region == "Гомельская"


def test_dossier_and_response_model_expose_grp_fallback_without_writing_history():
    company = Company(unp=400047301, source="grp", registration_date=date(1994, 4, 2))
    company.names_history = [CompanyNameHistory(full_name_ru="Гомельская птицефабрика")]
    place = CompanyPlaceLocation(
        unp=400047301, address="Гомельская обл., аг. Терешковичи", raw_json={"source": "grp"},
    )
    db = Mock()

    def query(model):
        q = Mock()
        for method in ("options", "filter", "order_by", "distinct", "limit"):
            getattr(q, method).return_value = q
        q.all.return_value = []
        q.first.return_value = company if model is Company else place if model is CompanyPlaceLocation else None
        return q

    db.query.side_effect = query
    dossier = CompanyCRUD(db).get_full_dossier(400047301)
    response = CompanyProfileResponse(**dossier).model_dump()
    assert response["addresses"][0]["full_address"] == place.address
    assert response["addresses"][0]["source"] == "grp"
    assert response["addresses"][0]["region"] == "Гомельская"
    assert response["addresses"][0]["valid_from"] is None
    assert response["place_location_address"] == place.address
    assert company.addresses_history == []
    db.add.assert_not_called()
    db.commit.assert_not_called()
