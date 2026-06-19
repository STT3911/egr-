"""Tests for the Bitrix24 thin-requisite helpers.

Покрытые сценарии:
  - _detect_is_ip: достоверный entity_type_id имеет приоритет над названием
  - _detect_is_ip: юрлицо с развёрнутым названием без аббревиатуры (регресс «ДЕФАЙНТ»)
  - _detect_is_ip: явные признаки ИП в названии / буквенный УНП
  - _detect_is_ip: при неопределённости возвращается организация (False)
  - _extract_director: срезает префикс «ИП»/«Индивидуальный предприниматель»
"""
from __future__ import annotations

import asyncio
import unittest

from app.api.v1.endpoints.bitrix import _detect_is_ip, _extract_director
from app.bitrix.bitrix_client import BitrixClient
from app.bitrix.requisite_service import _strip_country_prefix, _first_valid_email


class DetectIsIpTests(unittest.TestCase):
    def test_entity_type_juridical_wins_over_name(self):
        # Даже если в названии нет маркера юрлица, тип из ЕГР = 1 → организация.
        self.assertFalse(_detect_is_ip("ДЕФАЙНТ", "ДЕФАЙНТ", "291880617", entity_type_id=1))

    def test_entity_type_non_juridical_is_ip(self):
        self.assertTrue(_detect_is_ip("Иванов Иван Иванович", "Иванов И.И.", "291880617", entity_type_id=2))

    def test_spelled_out_org_without_abbreviation(self):
        # Регресс: «Общество с ограниченной ответственностью» без «ООО» — это юрлицо.
        full = 'Общество с ограниченной ответственностью "ДЕФАЙНТ"'
        short = 'ООО "ДЕФАЙНТ"'
        self.assertFalse(_detect_is_ip(full, short, "291880617", entity_type_id=None))

    def test_explicit_ip_prefix(self):
        self.assertTrue(_detect_is_ip("Индивидуальный предприниматель Петров П.П.", "", "123456789", None))
        self.assertTrue(_detect_is_ip("ИП Петров", "", "123456789", None))

    def test_letter_unp_is_ip(self):
        self.assertTrue(_detect_is_ip("Нечто", "", "AB1234567", None))

    def test_unknown_defaults_to_organization(self):
        # Нет ни типа, ни маркеров, УНП числовой → безопасный дефолт: организация.
        self.assertFalse(_detect_is_ip("Загадка", "Загадка", "123456789", None))


class ExtractDirectorTests(unittest.TestCase):
    def test_strips_full_prefix(self):
        self.assertEqual(
            _extract_director("Индивидуальный предприниматель Иванов Иван Иванович", ""),
            "Иванов Иван Иванович",
        )

    def test_strips_short_prefix(self):
        self.assertEqual(_extract_director("ИП Петров Пётр", ""), "Петров Пётр")

    def test_no_prefix_returns_source(self):
        self.assertEqual(_extract_director("Сидоров Сидор", ""), "Сидоров Сидор")


class MaskApplicationTests(unittest.TestCase):
    """Проверяем правило подстановки масок, применяемое в RequisiteService."""

    @staticmethod
    def _apply(mask: str, clean_name: str, unp: str) -> str:
        return (mask or "").replace("{company_name}", clean_name or "").replace("{company_unp}", unp)

    def test_both_variables_available_everywhere(self):
        # {company_unp} должен работать и в маске наименования, а не только в основании.
        out = self._apply("ИП {company_name} (УНП {company_unp})", "Иванов И.И.", "123456789")
        self.assertEqual(out, "ИП Иванов И.И. (УНП 123456789)")

    def test_no_double_prefix(self):
        # На вход маски идёт уже очищенное ФИО (director), префикс не задваивается.
        out = self._apply("Индивидуальный предприниматель {company_name}", "Иванов Иван Иванович", "123456789")
        self.assertEqual(out, "Индивидуальный предприниматель Иванов Иван Иванович")


class UpsertRequisiteAddressTests(unittest.TestCase):
    """Адрес реквизита пишется через crm.address.* с выбором add/update."""

    def _make_client(self, existing):
        client = BitrixClient(db=None)
        calls = []

        async def fake_call(method, params=None):
            calls.append((method, params))
            if method == "crm.address.list":
                return existing
            return True

        client.call = fake_call
        return client, calls

    def test_adds_when_no_existing_address(self):
        client, calls = self._make_client(existing=[])
        fields = {"ADDRESS_1": "г. Минск, ул. Ленина 1", "POSTAL_CODE": "220000", "PROVINCE": "Минская"}
        ok = asyncio.run(client.upsert_requisite_address(42, 6, fields))

        self.assertTrue(ok)
        methods = [m for m, _ in calls]
        self.assertEqual(methods, ["crm.address.list", "crm.address.add"])
        sent = calls[1][1]["fields"]
        self.assertEqual(sent["ENTITY_ID"], 42)
        self.assertEqual(sent["ENTITY_TYPE_ID"], BitrixClient.REQUISITE_ENTITY_TYPE_ID)
        self.assertEqual(sent["TYPE_ID"], 6)
        self.assertEqual(sent["ADDRESS_1"], "г. Минск, ул. Ленина 1")
        self.assertEqual(sent["POSTAL_CODE"], "220000")

    def test_updates_when_address_exists(self):
        client, calls = self._make_client(existing=[{"ENTITY_ID": 42, "TYPE_ID": 6, "ADDRESS_1": "старый"}])
        ok = asyncio.run(client.upsert_requisite_address(42, 6, {"ADDRESS_1": "новый"}))

        self.assertTrue(ok)
        methods = [m for m, _ in calls]
        self.assertEqual(methods, ["crm.address.list", "crm.address.update"])


class StripCountryPrefixTests(unittest.TestCase):
    def test_strips_republic_belarus(self):
        self.assertEqual(
            _strip_country_prefix("Республика Беларусь, 220037, г. Минск, пер. Козлова, д. 7"),
            "220037, г. Минск, пер. Козлова, д. 7",
        )

    def test_strips_short_belarus(self):
        self.assertEqual(_strip_country_prefix("Беларусь, г. Минск"), "г. Минск")

    def test_case_insensitive(self):
        self.assertEqual(_strip_country_prefix("РЕСПУБЛИКА БЕЛАРУСЬ, г. Брест"), "г. Брест")

    def test_no_prefix_unchanged(self):
        self.assertEqual(_strip_country_prefix("220037, г. Минск"), "220037, г. Минск")

    def test_none_returns_empty(self):
        self.assertEqual(_strip_country_prefix(None), "")


class FirstValidEmailTests(unittest.TestCase):
    def test_valid_single(self):
        self.assertEqual(_first_valid_email("info@company.by"), "info@company.by")

    def test_valid_with_dot_in_local(self):
        self.assertEqual(_first_valid_email("nikolay.piv@gmail.com"), "nikolay.piv@gmail.com")

    def test_picks_first_valid_from_list(self):
        self.assertEqual(_first_valid_email("мусор; a@b.by, c@d.by"), "a@b.by")

    def test_invalid_returns_none(self):
        self.assertIsNone(_first_valid_email("не email"))
        self.assertIsNone(_first_valid_email("foo@bar"))
        self.assertIsNone(_first_valid_email(""))
        self.assertIsNone(_first_valid_email(None))
        self.assertIsNone(_first_valid_email("почта@сайт.бел"))   # кириллица
        self.assertIsNone(_first_valid_email("info@domain.by."))  # висячая точка в домене
        self.assertIsNone(_first_valid_email("nikolay.piv.@gmail.com"))  # точка перед @
        self.assertIsNone(_first_valid_email("a..b@gmail.com"))   # двойная точка


if __name__ == "__main__":
    unittest.main()
