"""Tests for multi-tenant portal resolution (app.bitrix.tenancy.select_tenant).

Сценарий: приложение установлено на несколько порталов Б24. По данным вебхука/
установки (member_id, domain) нужно выбрать настройки именно того портала, а не
произвольного. Регресс к багу single-tenant (limit(1) / id=1).
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.bitrix.tenancy import select_tenant


def _portal(id, member_id, domain):
    return SimpleNamespace(id=id, bitrix_member_id=member_id, bitrix_domain=domain)


class SelectTenantTests(unittest.TestCase):
    def setUp(self):
        self.a = _portal(1, "memberA", "a.bitrix24.by")
        self.b = _portal(2, "memberB", "b.bitrix24.by")
        self.c = _portal(3, "memberC", "c.bitrix24.by")
        self.rows = [self.a, self.b, self.c]

    def test_picks_by_member_id(self):
        self.assertIs(select_tenant(self.rows, member_id="memberB"), self.b)

    def test_picks_by_member_id_other(self):
        self.assertIs(select_tenant(self.rows, member_id="memberC"), self.c)

    def test_member_id_priority_over_domain(self):
        # member_id указывает на A, домен — на B. Должен победить member_id.
        self.assertIs(select_tenant(self.rows, member_id="memberA", domain="b.bitrix24.by"), self.a)

    def test_falls_back_to_domain_when_member_unknown(self):
        # member_id не найден, но домен совпадает → выбираем по домену.
        self.assertIs(select_tenant(self.rows, member_id="ghost", domain="c.bitrix24.by"), self.c)

    def test_domain_only(self):
        self.assertIs(select_tenant(self.rows, domain="a.bitrix24.by"), self.a)

    def test_unknown_portal_returns_none(self):
        # Чужой/неустановленный портал → None (вебхук такой отклонит 403).
        self.assertIsNone(select_tenant(self.rows, member_id="stranger", domain="evil.bitrix24.by"))

    def test_no_identifiers_returns_none(self):
        self.assertIsNone(select_tenant(self.rows))

    def test_empty_rows_returns_none(self):
        self.assertIsNone(select_tenant([], member_id="memberA"))

    def test_member_id_int_coercion(self):
        # Битрикс может прислать member_id числом — сравнение по строке.
        row = _portal(5, "123456", "x.bitrix24.by")
        self.assertIs(select_tenant([row], member_id=123456), row)

    def test_ignores_rows_with_empty_member_id(self):
        # Старая запись без member_id не должна матчиться на пустой/любой member_id.
        legacy = _portal(1, None, "legacy.bitrix24.by")
        self.assertIsNone(select_tenant([legacy], member_id="memberA"))
        self.assertIs(select_tenant([legacy], domain="legacy.bitrix24.by"), legacy)


if __name__ == "__main__":
    unittest.main()
