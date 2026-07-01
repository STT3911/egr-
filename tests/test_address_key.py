"""Tests for building-level address normalization (app.utils.address_key)."""
from __future__ import annotations

import unittest

from app.utils.address_key import building_address_key


class BuildingAddressKeyTests(unittest.TestCase):
    def test_strips_apartment(self):
        self.assertEqual(
            building_address_key("г.Минск,ул.Карбышева,11,кв.108"),
            building_address_key("г.Минск,ул.Карбышева,11"),
        )

    def test_strips_office(self):
        self.assertEqual(
            building_address_key("г. Гродно, пр-т. Космонавтов, 15, оф. 5"),
            building_address_key("г. Гродно, пр-т. Космонавтов, 15"),
        )

    def test_country_prefix_ignored(self):
        self.assertEqual(
            building_address_key("Республика Беларусь, г. Минск, ул. Карбышева, д. 11"),
            building_address_key("г.Минск,ул.Карбышева,11"),
        )

    def test_dom_label_optional(self):
        # "д. 11" и голое "11" — один и тот же дом
        self.assertEqual(
            building_address_key("г. Минск, ул. Ленина, д. 11"),
            building_address_key("г. Минск, ул. Ленина, 11"),
        )

    def test_prospekt_abbreviation_equivalence(self):
        # "пр-т" и "проспект" должны схлопываться в один ключ (без мусорных остатков)
        self.assertEqual(
            building_address_key("г. Минск, пр-т Космонавтов, 15"),
            building_address_key("г. Минск, проспект Космонавтов, 15"),
        )

    def test_different_streets_do_not_match(self):
        self.assertNotEqual(
            building_address_key("г. Минск, ул. Ленина, 11"),
            building_address_key("г. Минск, ул. Карбышева, 11"),
        )

    def test_different_cities_same_street_do_not_match(self):
        # "Ленина" — частая улица, город обязан отличать
        self.assertNotEqual(
            building_address_key("г. Минск, ул. Ленина, 11"),
            building_address_key("г. Гродно, ул. Ленина, 11"),
        )

    def test_city_word_starting_with_g_not_corrupted(self):
        # регресс: "г" как метка не должна портить слова, начинающиеся с "г"
        key = building_address_key("г. Гродно, ул. Грушевая, 3")
        self.assertIn("гродно", key)
        self.assertIn("грушевая", key)

    def test_none_for_empty(self):
        self.assertIsNone(building_address_key(None))
        self.assertIsNone(building_address_key(""))

    def test_none_for_too_short_after_cleanup(self):
        # после отсечения квартиры остаётся почти ничего
        self.assertIsNone(building_address_key("кв. 5"))

    def test_apartment_marker_requires_digit(self):
        # "Комсомольская" не должна ложно триггерить маркер "ком" без цифры сразу после
        key = building_address_key("г. Минск, ул. Комсомольская, 5")
        self.assertIn("комсомольская", key)
        self.assertIn("5", key)


if __name__ == "__main__":
    unittest.main()
