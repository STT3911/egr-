#!/usr/bin/env python3
"""
Check companies from an Excel file against our DB and tax debt table.

Expected Excel shape:
- column A: company name
- column B: UNP

The script does not require openpyxl; it reads .xlsx as a ZIP/XML file.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.database.models import Company, NalogDebtRecord


NS_MAIN = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
NS_REL = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
NS_DOC_REL = {"r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


@dataclass
class ExcelCompanyRow:
    row_num: int
    source_name: str
    unp: int


def column_letters(cell_ref: str) -> str:
    match = re.match(r"([A-Z]+)", cell_ref or "")
    return match.group(1) if match else ""


def load_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        raw = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []

    root = ET.fromstring(raw)
    values: list[str] = []
    for si in root.findall("x:si", NS_MAIN):
        text_node = si.find("x:t", NS_MAIN)
        if text_node is not None and text_node.text is not None:
            values.append(text_node.text)
            continue

        parts = []
        for run in si.findall("x:r", NS_MAIN):
            node = run.find("x:t", NS_MAIN)
            if node is not None and node.text:
                parts.append(node.text)
        values.append("".join(parts))
    return values


def workbook_sheets(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall("r:Relationship", NS_REL)
    }

    result: list[tuple[str, str]] = []
    for sheet in workbook.findall("x:sheets/x:sheet", NS_MAIN):
        rid = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rel_map.get(rid or "")
        if not target:
            continue
        if not target.startswith("xl/"):
            target = f"xl/{target}"
        result.append((sheet.attrib.get("name", "Sheet"), target))
    return result


def cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    value_node = cell.find("x:v", NS_MAIN)
    if cell_type == "s" and value_node is not None and value_node.text:
        idx = int(value_node.text)
        return shared_strings[idx] if 0 <= idx < len(shared_strings) else ""
    if value_node is not None and value_node.text is not None:
        return value_node.text
    inline = cell.find("x:is/x:t", NS_MAIN)
    if inline is not None and inline.text is not None:
        return inline.text
    return ""


def parse_excel_rows(xlsx_path: Path, sheet_index: int = 0) -> list[ExcelCompanyRow]:
    with zipfile.ZipFile(xlsx_path) as zf:
        shared_strings = load_shared_strings(zf)
        sheets = workbook_sheets(zf)
        if not sheets:
            raise RuntimeError("No worksheets found in workbook")
        if sheet_index < 0 or sheet_index >= len(sheets):
            raise RuntimeError(f"Sheet index {sheet_index} out of range (total sheets: {len(sheets)})")

        sheet_name, sheet_target = sheets[sheet_index]
        root = ET.fromstring(zf.read(sheet_target))

        result: list[ExcelCompanyRow] = []
        for row in root.findall("x:sheetData/x:row", NS_MAIN):
            row_num = int(row.attrib.get("r", "0"))
            cells: dict[str, str] = {}
            for cell in row.findall("x:c", NS_MAIN):
                ref = cell.attrib.get("r", "")
                cells[column_letters(ref)] = cell_value(cell, shared_strings).strip()

            name = cells.get("A", "").strip()
            unp_raw = cells.get("B", "").strip()
            if not name or not unp_raw:
                continue
            if row_num == 1 and not unp_raw.isdigit():
                # header row
                continue

            digits = re.sub(r"\D", "", unp_raw)
            if not digits:
                continue

            result.append(ExcelCompanyRow(row_num=row_num, source_name=name, unp=int(digits)))

        if not result:
            raise RuntimeError(f"No usable company rows found in sheet '{sheet_name}'")
        return result


def chunked(items: list[int], size: int) -> Iterable[list[int]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare Excel company list with DB companies and tax debt records"
    )
    parser.add_argument("xlsx_path", help="Path to .xlsx file")
    parser.add_argument("--sheet-index", type=int, default=0, help="Worksheet index, default 0")
    parser.add_argument("--limit", type=int, default=30, help="How many example rows to print per section")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON summary instead of text report",
    )
    args = parser.parse_args()

    xlsx_path = Path(args.xlsx_path).expanduser()
    if not xlsx_path.exists():
        raise SystemExit(f"File not found: {xlsx_path}")

    rows = parse_excel_rows(xlsx_path, sheet_index=args.sheet_index)
    unps = sorted({row.unp for row in rows})

    db = SessionLocal()
    try:
        company_map: dict[int, str] = {}
        debt_counts: dict[int, int] = {}

        for batch in chunked(unps, 500):
            company_rows = (
                db.query(Company.unp, Company.current_name_ru)
                .filter(Company.unp.in_(batch))
                .all()
            )
            for unp, current_name_ru in company_rows:
                company_map[int(unp)] = current_name_ru or ""

            debt_rows = (
                db.query(NalogDebtRecord.debtor_unp)
                .filter(NalogDebtRecord.debtor_unp.in_(batch))
                .all()
            )
            for (debtor_unp,) in debt_rows:
                debt_counts[int(debtor_unp)] = debt_counts.get(int(debtor_unp), 0) + 1

        found_in_company = []
        missing_in_company = []
        with_debt = []
        without_debt = []

        for row in rows:
            if row.unp in company_map:
                found_in_company.append(row)
                if debt_counts.get(row.unp, 0) > 0:
                    with_debt.append(row)
                else:
                    without_debt.append(row)
            else:
                missing_in_company.append(row)

        summary = {
            "file": str(xlsx_path),
            "rows_total": len(rows),
            "unique_unps": len(unps),
            "found_in_egr_companies": len(found_in_company),
            "missing_in_egr_companies": len(missing_in_company),
            "with_tax_debt_records": len(with_debt),
            "without_tax_debt_records": len(without_debt),
            "examples": {
                "missing_in_egr_companies": [
                    {"row": row.row_num, "unp": row.unp, "name": row.source_name}
                    for row in missing_in_company[: args.limit]
                ],
                "without_tax_debt_records": [
                    {
                        "row": row.row_num,
                        "unp": row.unp,
                        "name_in_excel": row.source_name,
                        "name_in_db": company_map.get(row.unp) or None,
                    }
                    for row in without_debt[: args.limit]
                ],
                "with_tax_debt_records": [
                    {
                        "row": row.row_num,
                        "unp": row.unp,
                        "name_in_excel": row.source_name,
                        "name_in_db": company_map.get(row.unp) or None,
                        "debt_rows": debt_counts.get(row.unp, 0),
                    }
                    for row in with_debt[: args.limit]
                ],
            },
        }

        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0

        print("=" * 80)
        print("ПРОВЕРКА EXCEL ПО ЗАДОЛЖЕННОСТИ")
        print("=" * 80)
        print(f"Файл: {xlsx_path}")
        print(f"Строк в Excel: {len(rows)}")
        print(f"Уникальных УНП: {len(unps)}")
        print()
        print(f"Найдено в egr_companies: {len(found_in_company)}")
        print(f"Не найдено в egr_companies: {len(missing_in_company)}")
        print(f"Есть записи в nalog_debt_records: {len(with_debt)}")
        print(f"Нет записей в nalog_debt_records: {len(without_debt)}")
        print()

        if missing_in_company:
            print("Не найдены в egr_companies:")
            for row in missing_in_company[: args.limit]:
                print(f"  row={row.row_num} unp={row.unp} name={row.source_name}")
            print()

        if without_debt:
            print("Есть в egr_companies, но нет в nalog_debt_records:")
            for row in without_debt[: args.limit]:
                print(
                    f"  row={row.row_num} unp={row.unp} "
                    f"excel={row.source_name} db={company_map.get(row.unp) or '—'}"
                )
            print()

        if with_debt:
            print("Есть записи о задолженности:")
            for row in with_debt[: args.limit]:
                print(
                    f"  row={row.row_num} unp={row.unp} "
                    f"debt_rows={debt_counts.get(row.unp, 0)} "
                    f"excel={row.source_name}"
                )
            print()

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

