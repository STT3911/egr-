import csv
from datetime import date, datetime

from app.services.gias_contact_export import (
    ContactExportRow,
    _write_csv,
    collapse_contact_rows,
)
from app.services.company_contacts import is_current_contact_period


def _row(contact_type: str, value: str, value_norm: str, source: str):
    return ContactExportRow(
        unp="193913341",
        company_name='ООО "СигмаМед"',
        contact_type=contact_type,
        value=value,
        value_norm=value_norm,
        source=source,
        accreditation_state="ACTIVE",
        accreditation_from=datetime(2024, 1, 2, 10, 30),
        accreditation_to=None,
    )


def test_same_contact_is_deduplicated_and_sources_are_preserved() -> None:
    grouped = collapse_contact_rows(
        [
            _row("phone", "+375 29 352-61-99", "375293526199", "mart"),
            _row("phone", "+375293526199", "375293526199", "egr"),
            _row("email", "Office@Example.by", "office@example.by", "gias"),
        ]
    )

    assert grouped["phone"] == [
        {
            "unp": "193913341",
            "company_name": 'ООО "СигмаМед"',
            "contact": "+375 29 352-61-99",
            "accreditation_state": "ACTIVE",
            "accreditation_from": "2024-01-02",
            "accreditation_to": "",
            "sources": "egr|mart",
        }
    ]
    assert grouped["email"][0]["sources"] == "gias"


def test_csv_is_excel_friendly_and_keeps_russian_text(tmp_path) -> None:
    path = tmp_path / "phones.csv"
    rows = collapse_contact_rows(
        [_row("phone", "+375 29 352-61-99", "375293526199", "egr")]
    )["phone"]

    _write_csv(path, rows, ";")

    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        exported = list(csv.DictReader(handle, delimiter=";"))
    assert exported[0]["company_name"] == 'ООО "СигмаМед"'
    assert exported[0]["contact"] == "+375 29 352-61-99"


def test_egr_contact_period_excludes_expired_history() -> None:
    current = date(2026, 8, 14)

    assert not is_current_contact_period(
        date(2025, 9, 30), date(2026, 1, 4), current
    )
    assert is_current_contact_period(date(2026, 1, 5), None, current)
    assert is_current_contact_period(None, None, current)
    assert not is_current_contact_period(date(2026, 9, 1), None, current)
