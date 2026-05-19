import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.services.trade_registry_import import (
    dedupe_batch_by_registry_key,
    infer_source_date,
    row_to_payload,
)


class TradeRegistryImportParsingTest(unittest.TestCase):
    def test_infer_source_date_from_trade_registry_filename(self):
        self.assertEqual(
            infer_source_date(Path("Торговый реестр 14.05.2026.csv")),
            date(2026, 5, 14),
        )

    def test_row_to_payload_preserves_raw_json_and_parses_core_fields(self):
        csv_path = Path(tempfile.gettempdir()) / "Торговый реестр 14.05.2026.csv"
        row = {
            "Полное наименование юр. лица или ФИО ИП": "ООО Тест",
            "УНП": " 100200300 ",
            "Регистрационный номер в Торговом реестре": "TR-1",
            "Дата включения сведений в Торговый реестр": "14.05.2026",
            "Количество мест в объекте общественного питания (при наличии), ед.": "12",
            "Неизвестная колонка": "сохраняется",
        }

        payload = row_to_payload(row, csv_path, date(2026, 5, 14))

        self.assertIsNotNone(payload)
        self.assertEqual(payload["unp"], 100200300)
        self.assertEqual(payload["registration_number"], "TR-1")
        self.assertEqual(payload["inclusion_date"], date(2026, 5, 14))
        self.assertEqual(payload["seats_count"], 12)
        self.assertEqual(payload["raw_json"]["Неизвестная колонка"], "сохраняется")

    def test_dedupe_batch_by_registry_key_keeps_last_row(self):
        first = {"unp": 100200300, "registration_number": "TR-1", "object_name": "old"}
        second = {"unp": 100200300, "registration_number": "TR-1", "object_name": "new"}
        other = {"unp": 100200300, "registration_number": "TR-2", "object_name": "other"}

        rows, duplicates = dedupe_batch_by_registry_key([first, second, other])

        self.assertEqual(duplicates, 1)
        self.assertEqual(rows, [second, other])


if __name__ == "__main__":
    unittest.main()
