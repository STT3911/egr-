"""Tests for МАРТ object_contacts parsing (app.services.contact_parser.parse_contacts).

Примеры взяты из реальных данных trade_registry_records.
"""
from __future__ import annotations

import unittest

from app.services.contact_parser import parse_contacts


class ParseContactsTests(unittest.TestCase):
    def test_plus_375_phone(self):
        r = parse_contacts("+375296197299")
        self.assertEqual(r["phones"], ["+375296197299"])
        self.assertEqual(r["emails"], [])
        self.assertEqual(r["other"], [])

    def test_375_without_plus_normalized(self):
        self.assertEqual(parse_contacts("375296197299")["phones"], ["+375296197299"])

    def test_80_prefix_to_375(self):
        self.assertEqual(parse_contacts("80297651317")["phones"], ["+375297651317"])

    def test_mixed_phones_and_email(self):
        r = parse_contacts("+375291862380 +375172000209 adalvas@yandex.ru")
        self.assertEqual(r["phones"], ["+375291862380", "+375172000209"])
        self.assertEqual(r["emails"], ["adalvas@yandex.ru"])
        self.assertEqual(r["other"], [])

    def test_email_with_digits_not_a_phone(self):
        # регресс: цифры внутри email не должны попасть в телефоны
        r = parse_contacts("irina20092010@mail.ru")
        self.assertEqual(r["emails"], ["irina20092010@mail.ru"])
        self.assertEqual(r["phones"], [])

    def test_domain_goes_to_other(self):
        r = parse_contacts("optik.by")
        self.assertEqual(r["other"], ["optik.by"])
        self.assertEqual(r["emails"], [])
        self.assertEqual(r["phones"], [])

    def test_email_uppercase_normalized_lower(self):
        self.assertEqual(parse_contacts("Uni105@mail.ru")["emails"], ["uni105@mail.ru"])

    def test_two_space_separated_phones(self):
        self.assertEqual(
            parse_contacts("375172700712 375172702796")["phones"],
            ["+375172700712", "+375172702796"],
        )

    def test_dedup_same_phone_different_format(self):
        # +375296197299 и 375296197299 — один и тот же номер
        self.assertEqual(parse_contacts("+375296197299 375296197299")["phones"], ["+375296197299"])

    def test_dedup_email(self):
        self.assertEqual(
            parse_contacts("info@sam-masters.by info@sam-masters.by")["emails"],
            ["info@sam-masters.by"],
        )

    def test_typo_emails_kept_separately(self):
        # источник содержит и sam-masters.by, и sam-master.by — оба сохраняем как есть
        r = parse_contacts("info@sam-masters.by info@sam-master.by")
        self.assertEqual(r["emails"], ["info@sam-masters.by", "info@sam-master.by"])

    def test_phone_with_dashes_single_token(self):
        # дефисы внутри одного токена нормализуются (пробел в МАРТ — разделитель контактов,
        # поэтому номера с пробелами внутри не ожидаются — там это два разных контакта)
        self.assertEqual(parse_contacts("+375-29-619-72-99")["phones"], ["+375296197299"])

    def test_empty_and_none(self):
        for val in ("", "   ", None):
            self.assertEqual(parse_contacts(val), {"phones": [], "emails": [], "other": []})

    def test_broken_email_to_other(self):
        # «@» есть, но это не валидный email → other, не теряем
        self.assertEqual(parse_contacts("foo@bar")["other"], ["foo@bar"])


if __name__ == "__main__":
    unittest.main()
