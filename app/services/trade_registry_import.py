"""Trade registry CSV import helpers shared by CLI, Celery, and admin API."""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import re
import uuid
from collections import Counter
from datetime import date, datetime
from itertools import zip_longest
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.logger import get_logger
from app.database.models import (
    Company,
    TradeRegistryImportRun,
    TradeRegistryImportStage,
    TradeRegistryRecord,
)

logger = get_logger("trade_registry_import")

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
    (
        "shopping_center_catering_objects_count",
        "Количество объектов общественного питания, размещенных в торговом центре (при наличии), ед.",
    ),
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


def empty_trade_registry_stats() -> dict[str, Any]:
    return {
        "rows": 0,
        "valid": 0,
        "invalid": 0,
        "matched": 0,
        "missing_unp_in_db": 0,
        "egr_checked": 0,
        "egr_saved": 0,
        "egr_not_found": 0,
        "egr_errors": 0,
        "duplicate_registry_keys": 0,
        "deleted_old_records": 0,
        "written": 0,
        "encoding": None,
        "source_date": None,
    }


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


def company_map_for_batch(db: Session, payloads: list[dict[str, Any]]) -> dict[int, Any]:
    unps = sorted({int(payload["unp"]) for payload in payloads})
    rows = db.query(Company.unp, Company.id).filter(Company.unp.in_(unps)).all()
    return {int(unp): company_id for unp, company_id in rows}


def dedupe_batch_by_registry_key(payloads: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    deduped_by_key: dict[tuple[int, str], dict[str, Any]] = {}
    duplicates = 0
    for payload in payloads:
        key = (int(payload["unp"]), str(payload["registration_number"]))
        if key in deduped_by_key:
            duplicates += 1
        deduped_by_key[key] = payload
    return list(deduped_by_key.values()), duplicates


def upsert_batch(db: Session, payloads: list[dict[str, Any]]) -> None:
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


def import_csv(
    csv_path: Path,
    batch_size: int,
    dry_run: bool,
    source_date: date | None,
    encoding: str | None = None,
    missing_output: Path | None = None,
) -> dict[str, int | str | None]:
    """Original CLI import mode: upsert rows only for companies already in DB."""
    stats: dict[str, Any] = empty_trade_registry_stats()
    db = SessionLocal()
    missing_writer = CsvReportWriter(missing_output)
    try:
        resolved_encoding = encoding or detect_csv_encoding(csv_path)
        stats["encoding"] = resolved_encoding
        stats["source_date"] = source_date.isoformat() if source_date else None

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


def _json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _payload_to_stage_json(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: _json_safe(value) for key, value in payload.items()}


def _payload_from_stage_json(payload: dict[str, Any]) -> dict[str, Any]:
    restored = dict(payload)
    for key in ("source_date", "inclusion_date"):
        if restored.get(key):
            restored[key] = date.fromisoformat(restored[key])
    if restored.get("company_id"):
        restored["company_id"] = uuid.UUID(str(restored["company_id"]))
    return restored


async def _fetch_and_save_missing_companies(unps: list[int]) -> dict[int, tuple[bool, str | None]]:
    from app.services.aggregator import AggregatorService

    results: dict[int, tuple[bool, str | None]] = {}
    aggregator = AggregatorService()
    try:
        for unp in unps:
            try:
                fetched = await aggregator.fetch_and_save_raw(unp)
                if not fetched:
                    results[unp] = (False, None)
                    continue
                aggregator.process_raw_data(unp)
                results[unp] = (True, None)
            except Exception as exc:
                logger.warning("Failed to fetch missing EGR company %s: %s", unp, exc)
                results[unp] = (False, repr(exc))
    finally:
        aggregator.close()
    return results


def _fetch_missing_companies(unps: list[int]) -> dict[int, tuple[bool, str | None]]:
    if not unps:
        return {}
    return asyncio.run(_fetch_and_save_missing_companies(unps))


def _stage_payloads(db: Session, run_id: uuid.UUID, payloads: list[dict[str, Any]]) -> None:
    if not payloads:
        return
    values = [
        {
            "run_id": run_id,
            "unp": int(payload["unp"]),
            "registration_number": str(payload["registration_number"]),
            "company_id": payload["company_id"],
            "sync_hash": payload["sync_hash"],
            "payload_json": _payload_to_stage_json(payload),
        }
        for payload in payloads
    ]
    stmt = pg_insert(TradeRegistryImportStage).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            TradeRegistryImportStage.run_id,
            TradeRegistryImportStage.unp,
            TradeRegistryImportStage.registration_number,
        ],
        set_={
            "company_id": stmt.excluded.company_id,
            "sync_hash": stmt.excluded.sync_hash,
            "payload_json": stmt.excluded.payload_json,
            "updated_at": func.now(),
        },
    )
    db.execute(stmt)


def _update_run(db: Session, run: TradeRegistryImportRun, status: str | None, stats: dict[str, Any], error: str | None = None) -> None:
    if status is not None:
        run.status = status
    run.stats_json = stats
    run.error = error
    if status == "running" and run.started_at is None:
        run.started_at = datetime.utcnow()
    if status in {"success", "failed"}:
        run.finished_at = datetime.utcnow()
    run.updated_at = datetime.utcnow()
    db.add(run)
    db.commit()


def _apply_staged_import(db: Session, run_id: uuid.UUID, stats: dict[str, Any], batch_size: int) -> None:
    stage_unps = select(TradeRegistryImportStage.unp).where(TradeRegistryImportStage.run_id == run_id).distinct()
    delete_result = db.execute(delete(TradeRegistryRecord).where(TradeRegistryRecord.unp.in_(stage_unps)))
    stats["deleted_old_records"] = int(delete_result.rowcount or 0)

    last_stage_id = 0
    while True:
        rows = (
            db.query(TradeRegistryImportStage)
            .filter(TradeRegistryImportStage.run_id == run_id, TradeRegistryImportStage.id > last_stage_id)
            .order_by(TradeRegistryImportStage.id)
            .limit(batch_size)
            .all()
        )
        if not rows:
            break
        payloads = [_payload_from_stage_json(row.payload_json) for row in rows]
        db.execute(pg_insert(TradeRegistryRecord).values(payloads))
        stats["written"] += len(payloads)
        last_stage_id = int(rows[-1].id)

    db.query(TradeRegistryImportStage).filter(TradeRegistryImportStage.run_id == run_id).delete(synchronize_session=False)
    db.commit()


def run_admin_trade_registry_import(
    run_id: str | uuid.UUID,
    batch_size: int = 1000,
    encoding: str | None = None,
    fetch_missing_from_egr: bool = True,
) -> dict[str, Any]:
    """Admin mode: stage full CSV and replace records only for UNPs present in this CSV."""
    parsed_run_id = uuid.UUID(str(run_id))
    db = SessionLocal()
    stats = empty_trade_registry_stats()
    seen_keys: set[tuple[int, str]] = set()
    try:
        run = db.get(TradeRegistryImportRun, parsed_run_id)
        if run is None:
            raise RuntimeError(f"Trade registry import run {parsed_run_id} was not found")

        csv_path = Path(run.stored_path)
        source_date = run.source_date or infer_source_date(csv_path) or date.today()
        resolved_encoding = encoding or detect_csv_encoding(csv_path)
        stats["encoding"] = resolved_encoding
        stats["source_date"] = source_date.isoformat()
        _update_run(db, run, "running", stats)

        db.query(TradeRegistryImportStage).filter(TradeRegistryImportStage.run_id == parsed_run_id).delete()
        db.commit()

        def process_batch(batch_payloads: list[dict[str, Any]]) -> None:
            company_ids = company_map_for_batch(db, batch_payloads)
            missing_unps = sorted({int(payload["unp"]) for payload in batch_payloads if int(payload["unp"]) not in company_ids})
            if fetch_missing_from_egr and missing_unps:
                fetch_results = _fetch_missing_companies(missing_unps)
                stats["egr_checked"] += len(missing_unps)
                stats["egr_saved"] += sum(1 for ok, _ in fetch_results.values() if ok)
                stats["egr_not_found"] += sum(1 for ok, error in fetch_results.values() if not ok and not error)
                stats["egr_errors"] += sum(1 for ok, error in fetch_results.values() if not ok and error)
                company_ids = company_map_for_batch(db, batch_payloads)

            write_payloads_by_key: dict[tuple[int, str], dict[str, Any]] = {}
            for payload in batch_payloads:
                key = (int(payload["unp"]), str(payload["registration_number"]))
                if key in seen_keys:
                    stats["duplicate_registry_keys"] += 1
                else:
                    seen_keys.add(key)

                company_id = company_ids.get(payload["unp"])
                if company_id is None:
                    stats["missing_unp_in_db"] += 1
                    continue
                stats["matched"] += 1
                payload["company_id"] = company_id
                write_payloads_by_key[key] = payload

            _stage_payloads(db, parsed_run_id, list(write_payloads_by_key.values()))
            db.commit()
            _update_run(db, run, "running", stats)

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

        _apply_staged_import(db, parsed_run_id, stats, batch_size)
        _update_run(db, run, "success", stats)
        return stats
    except Exception as exc:
        db.rollback()
        try:
            run = db.get(TradeRegistryImportRun, parsed_run_id)
            if run is not None:
                _update_run(db, run, "failed", stats, repr(exc))
        except Exception:
            db.rollback()
        raise
    finally:
        db.close()


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import trade registry CSV for existing EGR UNPs only.")
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--encoding", default=None, help="CSV encoding; auto-detected when omitted")
    parser.add_argument("--missing-output", type=Path, default=None, help="Write rows with UNPs missing in DB to CSV")
    parser.add_argument("--source-date", type=parse_date, default=None)
    return parser
