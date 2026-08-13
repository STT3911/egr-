from app.utils.address_key import building_address_key, unit_address_key


def test_building_key_ignores_different_offices() -> None:
    first = "г. Минск, ул. Ленина, д. 10, оф. 15"
    second = "Минск, улица Ленина, дом 10, офис № 27"

    assert building_address_key(first) == building_address_key(second)
    assert unit_address_key(first) != unit_address_key(second)


def test_unit_key_matches_equivalent_exact_office() -> None:
    first = "Республика Беларусь, г. Минск, ул. Ленина, д. 10, оф. 15"
    second = "Минск, улица Ленина, дом 10, офис №15"

    assert unit_address_key(first) == unit_address_key(second)


def test_unit_key_requires_explicit_unit() -> None:
    assert unit_address_key("г. Минск, ул. Ленина, д. 10") is None


def test_apartment_and_office_are_not_the_same_unit() -> None:
    apartment = "г. Минск, ул. Ленина, д. 10, кв. 15"
    office = "г. Минск, ул. Ленина, д. 10, оф. 15"

    assert unit_address_key(apartment) != unit_address_key(office)
