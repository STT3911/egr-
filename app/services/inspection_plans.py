"""Import scheduled inspection plans from Excel workbooks."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

HEADER_ALIASES = {
    "plan_item_no": "№ пункта плана",
    "subject_unp": "УНП проверяемого субъекта",
    "subject_name": "Наименование проверяемого субъекта",
    "approving_authority": "Государственный орган, утвердивший сводный план проверок",
    "controller_unp": "УНП контролирующего (надзорного) органа",
    "controller_authority": "Наименование контролирующего (надзорного) органа",
    "executor_phone": "Контактный телефон исполнителя",
    "start_month": "Месяц начала проверки",
}

MONTHS = {
    "январь": 1,
    "февраль": 2,
    "март": 3,
    "апрель": 4,
    "май": 5,
    "июнь": 6,
    "июль": 7,
    "август": 8,
    "сентябрь": 9,
    "октябрь": 10,
    "ноябрь": 11,
    "декабрь": 12,
}

REGION_TITLE_MARKERS = {
    "брестской области": "Брестская область",
    "витебской области": "Витебская область",
    "гомельской области": "Гомельская область",
    "гродненской области": "Гродненская область",
    "минской области": "Минская область",
    "могилевской области": "Могилевская область",
    "могилёвской области": "Могилевская область",
    "г. минске": "г. Минск",
    "городе минске": "г. Минск",
}


@dataclass(frozen=True)
class ParsedInspectionRow:
    values: dict[str, Any]


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()
    if text.lower() in {"(пусто)", "пусто"}:
        return None
    return text or None


def parse_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = clean_text(value)
    if not text:
        return None
    digits = re.sub(r"\D+", "", text)
    return int(digits) if digits else None


def parse_unp(value: Any) -> int | None:
    parsed = parse_int(value)
    if parsed is None:
        return None
    digits = re.sub(r"\D+", "", str(parsed))
    return int(digits) if len(digits) == 9 else None


def normalize_header(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip().lower()


def stable_hash(payload: dict[str, Any]) -> str:
    dumped = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


def infer_period(title: str | None, fallback_file: Path) -> tuple[str, int | None, int | None]:
    source = " ".join(part for part in [title or "", fallback_file.name] if part)
    year_match = re.search(r"(20\d{2})", source)
    year = int(year_match.group(1)) if year_match else None
    lowered = source.lower()
    half = None
    if re.search(r"\b1\s*(?:полуг|п\/г|пг)", lowered) or "первое полугод" in lowered:
        half = 1
    elif re.search(r"\b2\s*(?:полуг|п\/г|пг)", lowered) or "второе полугод" in lowered:
        half = 2
    if year and half:
        return f"{year}-H{half}", year, half
    if year:
        return str(year), year, None
    return "unknown", None, None


def infer_region(title: str | None, fallback_file: Path) -> str:
    lowered = (title or "").lower().replace("ё", "е")
    for marker, region in REGION_TITLE_MARKERS.items():
        if marker.replace("ё", "е") in lowered:
            return region
    return fallback_file.parent.name


def month_no(value: str | None) -> int | None:
    if not value:
        return None
    return MONTHS.get(value.strip().lower())


def find_header_row(rows: list[tuple[Any, ...]]) -> tuple[int, dict[str, int]]:
    expected = {normalize_header(label): key for key, label in HEADER_ALIASES.items()}
    for row_idx, row in enumerate(rows, start=1):
        columns: dict[str, int] = {}
        for col_idx, value in enumerate(row):
            key = expected.get(normalize_header(value))
            if key:
                columns[key] = col_idx
        if {"subject_unp", "subject_name", "controller_authority", "start_month"}.issubset(columns):
            return row_idx, columns
    raise ValueError("Could not find inspection plan header row")


def iter_excel_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob("*.xlsx") if not p.name.startswith("~$"))


def parse_workbook(path: Path) -> list[ParsedInspectionRow]:
    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError("openpyxl is required for Excel import. Install requirements.txt first.") from exc

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    parsed: list[ParsedInspectionRow] = []
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        header_row_no, columns = find_header_row(rows)
        plan_title = next((clean_text(row[0]) for row in rows[: header_row_no - 1] if row and clean_text(row[0])), None)
        plan_period, plan_year, plan_half = infer_period(plan_title, path)
        source_region = infer_region(plan_title, path)
        current_subject: dict[str, Any] = {}

        for row_no, row in enumerate(rows[header_row_no:], start=header_row_no + 1):
            raw = {key: row[idx] if idx < len(row) else None for key, idx in columns.items()}
            if not any(clean_text(value) for value in raw.values()):
                continue

            plan_item_no = parse_int(raw.get("plan_item_no"))
            subject_unp = parse_unp(raw.get("subject_unp"))
            subject_name = clean_text(raw.get("subject_name"))
            if plan_item_no is not None or subject_unp is not None or subject_name:
                current_subject = {
                    "plan_item_no": plan_item_no,
                    "subject_unp": subject_unp,
                    "subject_name": subject_name,
                }
            if not current_subject.get("subject_unp") or not current_subject.get("subject_name"):
                continue

            start_month = clean_text(raw.get("start_month"))
            controller_authority = clean_text(raw.get("controller_authority"))
            if not controller_authority and not start_month:
                continue

            raw_json = {
                "source_values": {key: clean_text(value) for key, value in raw.items()},
                "source_region": source_region,
                "plan_title": plan_title,
            }
            identity = {
                "plan_period": plan_period,
                "source_region": source_region,
                "plan_item_no": current_subject.get("plan_item_no"),
                "subject_unp": current_subject["subject_unp"],
                "approving_authority": clean_text(raw.get("approving_authority")),
                "controller_unp": parse_unp(raw.get("controller_unp")),
                "controller_authority": controller_authority,
                "start_month": start_month,
            }
            values = {
                **identity,
                "company_id": None,
                "subject_name": current_subject["subject_name"],
                "plan_year": plan_year,
                "plan_half": plan_half,
                "plan_title": plan_title,
                "executor_phone": clean_text(raw.get("executor_phone")),
                "start_month_no": month_no(start_month),
                "source_file": str(path),
                "source_sheet": ws.title,
                "source_row_no": row_no,
                "raw_json": raw_json,
            }
            values["sync_key"] = stable_hash(identity)
            values["sync_hash"] = stable_hash({**values, "sync_key": None, "sync_hash": None})
            parsed.append(ParsedInspectionRow(values))
    return parsed


def parse_path(path: Path) -> list[ParsedInspectionRow]:
    rows: list[ParsedInspectionRow] = []
    for file_path in iter_excel_files(path):
        rows.extend(parse_workbook(file_path))
    return rows


def company_map_for_unps(db: Any, unps: set[int]) -> dict[int, Any]:
    from app.database.models import Company

    if not unps:
        return {}
    rows = db.query(Company.unp, Company.id).filter(Company.unp.in_(sorted(unps))).all()
    return {int(unp): company_id for unp, company_id in rows}


def import_inspection_plan_rows(
    db: Any,
    rows: Iterable[ParsedInspectionRow],
    *,
    batch_size: int = 500,
    dry_run: bool = False,
) -> dict[str, int]:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.database.models import InspectionPlanRecord

    materialized = [row.values.copy() for row in rows]
    stats = {
        "parsed": len(materialized),
        "matched_companies": 0,
        "created_or_updated": 0,
        "dry_run": int(dry_run),
    }
    unps = {int(row["subject_unp"]) for row in materialized if row.get("subject_unp")}
    company_ids = company_map_for_unps(db, unps)
    now = datetime.utcnow()
    for row in materialized:
        row["company_id"] = company_ids.get(int(row["subject_unp"]))
        if row["company_id"]:
            stats["matched_companies"] += 1
        row["last_seen_at"] = now
        row["updated_at"] = now

    if dry_run or not materialized:
        return stats

    for offset in range(0, len(materialized), batch_size):
        batch = materialized[offset : offset + batch_size]
        stmt = pg_insert(InspectionPlanRecord).values(batch)
        excluded = stmt.excluded
        update_columns = {
            column.name: getattr(excluded, column.name)
            for column in InspectionPlanRecord.__table__.columns
            if column.name not in {"id", "sync_key", "first_seen_at", "created_at"}
        }
        stmt = stmt.on_conflict_do_update(
            constraint="uq_inspection_plan_records_sync_key",
            set_=update_columns,
        )
        db.execute(stmt)
        stats["created_or_updated"] += len(batch)
    db.commit()
    return stats


def import_inspection_plan_path(
    db: Any,
    path: Path,
    *,
    batch_size: int = 500,
    dry_run: bool = False,
) -> dict[str, int]:
    return import_inspection_plan_rows(db, parse_path(path), batch_size=batch_size, dry_run=dry_run)
