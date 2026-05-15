"""Import Belarus trade registry CSV rows for UNPs already present in EGR DB.

Usage:
  python scripts/import_trade_registry_csv.py "C:\\path\\to\\trade_registry.csv" --dry-run
  python scripts/import_trade_registry_csv.py "C:\\path\\to\\trade_registry.csv"
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import date, datetime
from itertools import zip_longest
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CSV_FIELDS = [
    ("legal_name", "Полное наименование юр. лица или ФИО ИП"),
    ("unp", "УНП"),
    ("legal_address", "Место нахождения юр. лица/место жительства ИП"),
    ("object_type", "Тип объекта"),
    ("object_name", "Наименование объекта/доменное имя интернет-магазина"),
    ("internet_shop_domain", "Наименование объекта/доменное имя интернет-магазина__2"),
    ("trade_network_name", "Название торговой сети (при наличии)"),
    ("object_region", "Место нахождения объекта: область"),
    ("object_district", "Место нахождения объекта: район"),
    ("object_locality", "Место нахождения объекта: населенный пункт"),
    ("object_street", "Место нахождения объекта: улица"),
    ("object_building", "Место нахождения объекта: дом и корпус"),
    ("object_office", "Место нахождения объекта: квартира/офис"),
    ("object_contacts", "Контакты объекта"),
    ("format_type", "Вид торгового объекта в зависимости от формата"),
    ("location_type", "Вид объекта в зависимости от места расположения"),
    ("assortment_type", "Вид торгового объекта в зависимости от ассортимента товаров"),
    ("is_firm", 'Вид торгового объекта в зависимости от способа организации торговли "Фирменный"'),
    ("trade_object_type", "Тип торгового объекта (при наличии)"),
    ("trade_area", "Торговая площадь торгового объекта (при наличии), кв. м"),
    ("retail_trade", 'Вид торговли "Розничная"'),
    ("wholesale_trade", 'Вид торговли "Оптовая"'),
    ("retail_without_object_form", "Форма розничной торговли без использования торгового объекта"),
    ("wholesale_without_object", "Оптовая торговля без использования торгового объекта"),
    ("goods_classes", "Классы реализуемых товаров"),
    ("goods_groups", "Группы реализуемых товаров"),
    ("goods_subgroups", "Подгруппы реализуемых товаров"),
    ("catering_format_type", "Тип объекта общественного питания в зависимости от формата (при наличии)"),
    ("seats_count", "Количество мест в объекте общественного питания (при наличии), ед."),
    ("public_seats_count", "Количество общедоступных мест в объекте общественного питания (при наличии), ед."),
    ("shopping_center_specializations", "Специализации торгового центра"),
    ("shopping_center_trade_objects_count", "Количество торговых объектов, размещенных в торговом центре, ед."),
    ("shopping_center_catering_objects_count", "Количество объектов общественного питания, размещенных в торговом центре (при наличии), ед."),
    ("shopping_center_trade_area", "Площадь торгового центра, отведенная под торговые объекты, кв. м"),
    ("market_type", "Тип рынка"),
    ("market_specialization", "Специализация рынка (при наличии)"),
    ("market_places_count", "Количество торговых мест, размещенных на территории рынка, ед."),
    ("market_trade_objects_count", "Количество торговых объектов, размещенных на территории рынка, ед."),
    ("registration_number", "Регистрационный номер в Торговом реестре"),
    ("inclusion_date", "Дата включения сведений в Торговый реестр"),
]

INTEGER_FIELDS = {
    "seats_count",
    "public_seats_count",
    "shopping_center_trade_objects_count",
    "shopping_center_catering_objects_count",
    "market_places_count",
    "market_trade_objects_count",
}

DATE_FIELDS = {"inclusion_date"}
UPSERT_SKIP_FIELDS = {"id", "first_seen_at", "created_at"}


def make_unique_headers(headers: list[str]) -> list[str]:
    seen: Counter[str] = Counter()
    unique = []
    for header in headers:
        clean = header.strip()
        seen[clean] += 1
        unique.append(clean if seen[clean] == 1 else f"{clean}__{seen[clean]}")
    return unique


def row_from_values(headers: list[str], values: list[str]) -> dict[str, str | None]:
    row = {}
    for index, (header, value) in enumerate(zip_longest(headers, values), start=1):
        key = header if header is not None else f"__extra_column_{index}"
        row[key] = value
    return row


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_unp(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    return int(digits)


def parse_int(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    normalized = text.replace(" ", "").replace(",", ".")
    try:
        return int(float(normalized))
    except ValueError:
        return None


def parse_date(value: Any) -> date | None:
    text = clean_text(value)
    if not text:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def infer_source_date(csv_path: Path) -> date | None:
    match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", csv_path.name)
    if not match:
        return None
    day, month, year = match.groups()
    return date(int(year), int(month), int(day))


def detect_csv_encoding(csv_path: Path) -> str:
    sample = csv_path.read_bytes()[:8192]
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            sample.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8-sig"


def hash_payload(payload: dict[str, Any]) -> str:
    dumped = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


def row_to_payload(row: dict[str, str], csv_path: Path, source_date: date | None) -> dict[str, Any] | None:
    raw_json = {key: clean_text(value) for key, value in row.items()}
    payload: dict[str, Any] = {"raw_json": raw_json}

    for target, source in CSV_FIELDS:
        value = raw_json.get(source)
        if target == "unp":
            payload[target] = parse_unp(value)
        elif target in INTEGER_FIELDS:
            payload[target] = parse_int(value)
        elif target in DATE_FIELDS:
            payload[target] = parse_date(value)
        else:
            payload[target] = clean_text(value)

    if payload["unp"] is None or not payload["registration_number"]:
        return None

    payload["source_date"] = source_date
    payload["source_file"] = str(csv_path)
    payload["sync_hash"] = hash_payload(raw_json)
    return payload


def batched(items: Iterable[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def iter_payloads(csv_path: Path, source_date: date | None, encoding: str | None = None) -> Iterable[dict[str, Any] | None]:
    resolved_encoding = encoding or detect_csv_encoding(csv_path)
    with csv_path.open("r", encoding=resolved_encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=";", quotechar='"')
        try:
            headers = make_unique_headers(next(reader))
        except StopIteration:
            return

        for values in reader:
            row = row_from_values(headers, values)
            yield row_to_payload(row, csv_path, source_date)


def company_map_for_batch(db, payloads: list[dict[str, Any]]) -> dict[int, Any]:
    from app.database.models import Company

    unps = sorted({payload["unp"] for payload in payloads})
    rows = db.query(Company.unp, Company.id).filter(Company.unp.in_(unps)).all()
    return {int(unp): company_id for unp, company_id in rows}


def upsert_batch(db, payloads: list[dict[str, Any]]) -> None:
    from sqlalchemy import func
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.database.models import TradeRegistryRecord

    stmt = pg_insert(TradeRegistryRecord).values(payloads)
    update_values = {
        column.name: getattr(stmt.excluded, column.name)
        for column in TradeRegistryRecord.__table__.columns
        if column.name not in UPSERT_SKIP_FIELDS
        and column.name not in {"unp", "registration_number", "last_seen_at", "updated_at"}
    }
    update_values["last_seen_at"] = func.now()
    update_values["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(
        index_elements=[TradeRegistryRecord.unp, TradeRegistryRecord.registration_number],
        set_=update_values,
    )
    db.execute(stmt)


class CsvReportWriter:
    def __init__(self, path: Path | None):
        self.path = path
        self.handle = None
        self.writer = None
        self.fieldnames = None

    def write(self, row: dict[str, Any]) -> None:
        if self.path is None:
            return
        if self.writer is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.fieldnames = list(row.keys())
            self.handle = self.path.open("w", encoding="utf-8-sig", newline="")
            self.writer = csv.DictWriter(self.handle, fieldnames=self.fieldnames, extrasaction="ignore")
            self.writer.writeheader()
        self.writer.writerow(row)

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None


def dedupe_batch_by_registry_key(payloads: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    deduped_by_key: dict[tuple[int, str], dict[str, Any]] = {}
    duplicates = 0
    for payload in payloads:
        key = (int(payload["unp"]), str(payload["registration_number"]))
        if key in deduped_by_key:
            duplicates += 1
        deduped_by_key[key] = payload
    return list(deduped_by_key.values()), duplicates


def import_csv(
    csv_path: Path,
    batch_size: int,
    dry_run: bool,
    source_date: date | None,
    encoding: str | None = None,
    missing_output: Path | None = None,
) -> dict[str, int | str | None]:
    from app.core.database import SessionLocal

    stats = {
        "rows": 0,
        "valid": 0,
        "invalid": 0,
        "matched": 0,
        "missing_unp_in_db": 0,
        "duplicate_registry_keys": 0,
        "written": 0,
    }
    db = SessionLocal()
    missing_writer = CsvReportWriter(missing_output)
    try:
        resolved_encoding = encoding or detect_csv_encoding(csv_path)
        stats["encoding"] = resolved_encoding

        def process_batch(batch_payloads: list[dict[str, Any]]) -> None:
            company_ids = company_map_for_batch(db, batch_payloads)
            write_payloads = []
            for payload in batch_payloads:
                company_id = company_ids.get(payload["unp"])
                if company_id is None:
                    stats["missing_unp_in_db"] += 1
                    missing_writer.write(
                        {
                            "__parsed_unp": payload["unp"],
                            "__registration_number": payload["registration_number"],
                            **payload["raw_json"],
                        }
                    )
                    continue
                stats["matched"] += 1
                payload["company_id"] = company_id
                write_payloads.append(payload)

            write_payloads, duplicates = dedupe_batch_by_registry_key(write_payloads)
            stats["duplicate_registry_keys"] += duplicates

            if dry_run or not write_payloads:
                return

            upsert_batch(db, write_payloads)
            db.commit()
            stats["written"] += len(write_payloads)

        batch = []
        for payload in iter_payloads(csv_path, source_date, resolved_encoding):
            stats["rows"] += 1
            if payload is None:
                stats["invalid"] += 1
                continue
            stats["valid"] += 1
            batch.append(payload)
            if len(batch) < batch_size:
                continue

            process_batch(batch)
            batch = []

        if batch:
            process_batch(batch)

        if dry_run:
            db.rollback()
        return stats
    except Exception:
        db.rollback()
        raise
    finally:
        missing_writer.close()
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import trade registry CSV for existing EGR UNPs only.")
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--encoding", default=None, help="CSV encoding; auto-detected when omitted")
    parser.add_argument("--missing-output", type=Path, default=None, help="Write rows with UNPs missing in DB to CSV")
    parser.add_argument("--source-date", type=parse_date, default=None)
    args = parser.parse_args()

    if not args.csv_path.exists():
        raise FileNotFoundError(args.csv_path)
    if args.batch_size < 1:
        parser.error("--batch-size must be greater than zero")

    source_date = args.source_date or infer_source_date(args.csv_path)
    stats = import_csv(
        args.csv_path,
        args.batch_size,
        args.dry_run,
        source_date,
        args.encoding,
        args.missing_output,
    )
    print(json.dumps({**stats, "source_date": source_date.isoformat() if source_date else None}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
