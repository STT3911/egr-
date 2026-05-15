import unittest

from app.telegram_bot.formatting import (
    HELP_TEXT,
    format_company_card,
    format_lookup_message,
    lookup_keyboard,
)
from app.telegram_bot.runner import TelegramBot


class FakeTelegram:
    def __init__(self):
        self.messages = []
        self.answered_callbacks = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.messages.append(
            {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        )

    async def answer_callback_query(self, callback_query_id):
        self.answered_callbacks.append(callback_query_id)


class FakeEGR:
    def __init__(self):
        self.lookup_calls = []
        self.company_calls = []
        self.lookup_results = []
        self.company = {
            "unp": 500000306,
            "current_name_ru": "Тестовая компания",
            "current_status_name": "Действующий",
            "registration_date": "2020-01-01",
            "place_location_address": "Минск, ул. Тестовая, 1",
            "ved": [{"ved_code": "62010", "ved_name": "Разработка ПО"}],
            "contacts": [{"email": "info@example.com", "phone": "+375 17 000-00-00"}],
        }

    async def lookup(self, query, limit):
        self.lookup_calls.append((query, limit))
        return self.lookup_results

    async def get_company(self, unp):
        self.company_calls.append(unp)
        return self.company


class TelegramFormattingTests(unittest.TestCase):
    def test_format_company_card_with_optional_fields(self):
        card = format_company_card(
            {
                "unp": 500000306,
                "current_name_ru": "ООО «Рога & Копыта»",
                "current_status_name": "Действующий",
                "registration_date": "2020-01-01",
                "liquidation_date": None,
                "addresses": [{"full_address": "Минск"}],
                "ved": [{"ved_code": "62010", "ved_name": "Разработка ПО"}],
                "contacts": [{"website": "https://example.com"}],
            }
        )

        self.assertIn("<b>ООО «Рога &amp; Копыта»</b>", card)
        self.assertIn("УНП: <code>500000306</code>", card)
        self.assertIn("<b>Адреса</b>", card)
        self.assertIn("1. Минск", card)
        self.assertIn("<b>ВЭД</b>", card)
        self.assertIn("1. 62010 Разработка ПО", card)
        self.assertIn("сайт: https://example.com", card)

    def test_format_lookup_message_includes_historical_match(self):
        message = format_lookup_message(
            "рога",
            [
                {
                    "unp": 500000306,
                    "full_name_ru": "ООО Рога",
                    "matched_name": "ЗАО Старые Рога",
                    "matched_historical_name": True,
                }
            ],
        )

        self.assertIn("Нашёл 1 вариантов", message)
        self.assertIn("Найдено по прежнему названию: ЗАО Старые Рога", message)

    def test_lookup_keyboard_uses_company_callbacks(self):
        keyboard = lookup_keyboard(
            [{"unp": 500000306, "full_name_ru": "Очень длинное название компании"}]
        )

        self.assertEqual(
            keyboard["inline_keyboard"][0][0]["callback_data"],
            "company:500000306",
        )


class TelegramBotRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.telegram = FakeTelegram()
        self.egr = FakeEGR()
        self.bot = TelegramBot(self.telegram, self.egr, lookup_limit=5)

    async def test_start_command_sends_help(self):
        await self.bot.process_update(
            {"message": {"chat": {"id": 10}, "text": "/start"}}
        )

        self.assertEqual(self.telegram.messages[0]["text"], HELP_TEXT)
        self.assertEqual(self.egr.lookup_calls, [])
        self.assertEqual(self.egr.company_calls, [])

    async def test_unp_message_opens_company_card(self):
        await self.bot.process_update(
            {"message": {"chat": {"id": 10}, "text": "500000306"}}
        )

        self.assertEqual(self.egr.company_calls, ["500000306"])
        self.assertIn("Тестовая компания", self.telegram.messages[0]["text"])
        self.assertEqual(
            self.telegram.messages[0]["reply_markup"]["inline_keyboard"][0][0][
                "callback_data"
            ],
            "company:500000306",
        )

    async def test_name_message_uses_lookup(self):
        self.egr.lookup_results = [{"unp": 500000306, "full_name_ru": "ООО Рога"}]

        await self.bot.process_update(
            {"message": {"chat": {"id": 10}, "text": "рога"}}
        )

        self.assertEqual(self.egr.lookup_calls, [("рога", 5)])
        self.assertIn("ООО Рога", self.telegram.messages[0]["text"])
        self.assertEqual(
            self.telegram.messages[0]["reply_markup"]["inline_keyboard"][0][0][
                "callback_data"
            ],
            "company:500000306",
        )

    async def test_short_text_sends_help(self):
        await self.bot.process_update({"message": {"chat": {"id": 10}, "text": " "}})

        self.assertEqual(self.telegram.messages[0]["text"], HELP_TEXT)
        self.assertEqual(self.egr.lookup_calls, [])

    async def test_company_callback_opens_company_card(self):
        await self.bot.process_update(
            {
                "callback_query": {
                    "id": "cb-1",
                    "data": "company:500000306",
                    "message": {"chat": {"id": 10}},
                }
            }
        )

        self.assertEqual(self.telegram.answered_callbacks, ["cb-1"])
        self.assertEqual(self.egr.company_calls, ["500000306"])
        self.assertIn("Тестовая компания", self.telegram.messages[0]["text"])


if __name__ == "__main__":
    unittest.main()
