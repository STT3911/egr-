"""Synchronization service for bankrot.gov.by bankruptcy cases.

Алгоритм:
  1. Создаём запись BankrotSyncRun (status='running').
  2. Итерируемся по всем делам через BankrotClient.iter_all_cases().
  3. Для каждого дела:
       – запрашиваем GET /cases/{id}            (detail_data)
       – запрашиваем GET /cases/{id}/judgements/group (judgements_group)
       – ошибки одного дела не прерывают синхронизацию; сохраняем в fetch_error
       – извлекаем UNP по цепочке приоритетов; при отсутствии — NULL + warning
  4. Каждые save_every дел:
       – bulk-upsert в bankrot_cases (INSERT … ON CONFLICT DO UPDATE)
       – дозаписываем строки в JSONL-файл
       – обновляем счётчики в BankrotSyncRun
  5. После итерации — финальный flush.
  6. Переименовываем .tmp → .jsonl (атомарная операция).
  7. Обновляем BankrotSyncRun (status='done' / 'failed').
"""
from __future__ import annotations

import json
import time
import traceback
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.core.logger import get_logger
from app.database.models import BankrotCase, BankrotCaseDataset, BankrotSyncRun
from app.services.bankrot_client import BankrotClient, BankrotAPIError

logger = get_logger("bankrot.sync")


# ---------------------------------------------------------------------------
# UNP extraction helpers
# ---------------------------------------------------------------------------

def _dig(data: Any, *keys: str) -> Any:
    """Безопасный обход вложенных dict по цепочке ключей."""
    cur = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def extract_unp(
    list_data: Optional[Dict[str, Any]],
    detail_data: Optional[Dict[str, Any]],
) -> Optional[int]:
    """Извлечь УНП с приоритетом detail_data над list_data.

    Цепочка поиска (первый непустой):
      1. detail_data → debtorModel.organization.unp
      2. detail_data → organization.unp
      3. list_data   → debtorModel.organization.unp
      4. list_data   → organization.unp

    Returns:
        int УНП или None, если не найден ни в одном источнике.
    """
    candidates: List[Any] = []
    if detail_data:
        candidates.append(_dig(detail_data, "debtorModel", "organization", "unp"))
        candidates.append(_dig(detail_data, "organization", "unp"))
    if list_data:
        candidates.append(_dig(list_data, "debtorModel", "organization", "unp"))
        candidates.append(_dig(list_data, "organization", "unp"))

    for val in candidates:
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                continue
    return None


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

def _parse_date(value: Any) -> Optional[date]:
    """Разобрать дату из ISO-строки (с временем или без)."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        # "2020-01-15T00:00:00" → берём первые 10 символов
        return datetime.fromisoformat(str(value)[:10]).date()
    except (ValueError, TypeError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value) if not isinstance(value, str) else value


def extract_debtor_id(
    list_data: Optional[Dict], detail_data: Optional[Dict]
) -> Optional[int]:
    """Извлечь внутренний id должника для поиска его публикаций."""
    for source in (detail_data or {}, list_data or {}):
        for path in (("debtorModel", "id"), ("debtor", "id")):
            value = _safe_int(_dig(source, *path))
            if value is not None:
                return value
    return None


def extract_debtor_name(
    list_data: Optional[Dict], detail_data: Optional[Dict]
) -> Optional[str]:
    """Извлечь наименование должника для публичного поиска сообщений."""
    paths = (
        ("debtorModel", "organization", "shortName"),
        ("debtorModel", "organization", "fullName"),
        ("organization", "shortName"),
        ("organization", "fullName"),
        ("debtor", "value"),
    )
    for source in (detail_data or {}, list_data or {}):
        for path in paths:
            value = _safe_str(_dig(source, *path))
            if value and value.strip():
                return value.strip()
    return None


def extract_manager_id(
    list_data: Optional[Dict], detail_data: Optional[Dict]
) -> Optional[int]:
    """Извлечь внутренний id управляющего из живой и прежней схем API."""
    for source in (detail_data or {}, list_data or {}):
        for path in (("manager", "id"), ("managerModel", "id")):
            value = _safe_int(_dig(source, *path))
            if value is not None:
                return value
    return None


def _extract_fields(
    list_data: Optional[Dict],
    detail_data: Optional[Dict],
) -> Dict[str, Any]:
    """Извлечь структурированные поля из API-данных.

    detail_data имеет приоритет над list_data.
    """
    primary = detail_data or {}
    secondary = list_data or {}

    def get(*keys: str) -> Any:
        v = _dig(primary, *keys)
        if v is None:
            v = _dig(secondary, *keys)
        return v

    manager_name = (
        _dig(primary, "manager", "fullName")
        or _dig(primary, "manager", "name")
        or _dig(primary, "managerModel", "fullName")
        or _dig(primary, "managerModel", "name")
        or _dig(secondary, "manager", "fullName")
        or _dig(secondary, "manager", "name")
        or _dig(secondary, "managerModel", "fullName")
        or _dig(secondary, "managerModel", "name")
    )

    return {
        "number":         _safe_str(get("number")),
        "start_date":     _parse_date(get("startDate")),
        "end_date":       _parse_date(get("endDate")),
        "status":         _safe_int(get("status")),
        "procedure_type": _safe_int(get("procedureType")),
        "court":          _safe_str(get("court")),
        "judge":          _safe_str(get("judge")),
        "manager_id":     _safe_int(
            _dig(primary, "manager", "id")
            or _dig(primary, "managerModel", "id")
            or _dig(secondary, "manager", "id")
            or _dig(secondary, "managerModel", "id")
        ),
        "manager_name":   _safe_str(manager_name),
        "last_judgment_id": _safe_int(get("lastJudgmentId")),
    }


def _build_row(
    case_id: int,
    list_data: Optional[Dict],
    detail_data: Optional[Dict],
    judgements_group: Optional[Dict],
    unp: Optional[int],
    fetch_error: Optional[str],
) -> Dict[str, Any]:
    """Сформировать dict для bulk-upsert в bankrot_cases."""
    fields = _extract_fields(list_data, detail_data)
    return {
        "case_id":          case_id,
        "debtor_unp":       unp,
        **fields,
        "list_data":        list_data,
        "detail_data":      detail_data,
        "judgements_group": judgements_group,
        "fetch_error":      fetch_error,
        "updated_at":       datetime.utcnow(),
        # created_at намеренно не включаем — server_default при INSERT,
        # и не обновляем при UPDATE (см. _upsert_cases)
    }


# ---------------------------------------------------------------------------
# DB upsert
# ---------------------------------------------------------------------------

def _emit_bankruptcy_events(db: Session, rows: List[Dict[str, Any]]) -> None:
    """Поставить события подписки bankruptcy: новое дело или смена статуса по UNP.

    Сравниваем входящие строки с текущим состоянием bankrot_cases (case_id → status)
    одним запросом. emit_company_event сам отсекает неотслеживаемые UNP.
    НЕ коммитит — коммит делает _upsert_cases ниже.
    """
    try:
        from app.services.subscription_events import emit_company_event, EVENT_BANKRUPTCY

        case_ids = [r["case_id"] for r in rows if r.get("case_id") is not None]
        if not case_ids:
            return
        existing = {
            cid: status
            for cid, status in db.query(BankrotCase.case_id, BankrotCase.status)
            .filter(BankrotCase.case_id.in_(case_ids))
            .all()
        }
        for r in rows:
            unp = r.get("debtor_unp")
            if unp is None:
                continue
            case_id = r.get("case_id")
            new_status = r.get("status")
            if case_id not in existing:
                emit_company_event(
                    db, unp, EVENT_BANKRUPTCY,
                    new_value=f"дело {r.get('number')}, статус {new_status}",
                )
            elif existing[case_id] != new_status:
                emit_company_event(
                    db, unp, EVENT_BANKRUPTCY,
                    old_value=existing[case_id], new_value=new_status,
                )
    except Exception:
        # Эмиссия событий не должна валить синхронизацию банкротства.
        pass


def _upsert_cases(db: Session, rows: List[Dict[str, Any]]) -> None:
    """Bulk INSERT … ON CONFLICT (case_id) DO UPDATE для bankrot_cases.

    Обновляет все колонки кроме case_id и created_at.
    """
    if not rows:
        return

    # До upsert: детект новых дел / смены статуса для подписчиков.
    _emit_bankruptcy_events(db, rows)

    stmt = pg_insert(BankrotCase).values(rows)

    update_cols = {
        col: stmt.excluded[col]
        for col in rows[0]
        if col not in ("case_id", "created_at")
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=["case_id"],
        set_=update_cols,
    )
    db.execute(stmt)
    db.commit()


def _upsert_case_datasets(db: Session, rows: List[Dict[str, Any]]) -> None:
    """Upsert дочерних наборов без потери последнего успешного payload."""
    if not rows:
        return

    stmt = pg_insert(BankrotCaseDataset).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["case_id", "dataset_type"],
        set_={
            "endpoint": stmt.excluded.endpoint,
            "http_method": stmt.excluded.http_method,
            "payload": func.coalesce(
                stmt.excluded.payload, BankrotCaseDataset.payload
            ),
            "fetch_error": stmt.excluded.fetch_error,
            "fetched_at": func.coalesce(
                stmt.excluded.fetched_at, BankrotCaseDataset.fetched_at
            ),
            "updated_at": stmt.excluded.updated_at,
        },
    )
    db.execute(stmt)
    db.commit()


# ---------------------------------------------------------------------------
# Main sync function
# ---------------------------------------------------------------------------

def sync_bankrot_cases(
    db: Session,
    *,
    page_size: Optional[int] = None,
    delay: Optional[float] = None,
    detail_delay: Optional[float] = None,
    output_dir: Optional[str] = None,
    save_every: Optional[int] = None,
    token: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    fetch_related_data: Optional[bool] = None,
    related_page_size: Optional[int] = None,
    related_max_pages: Optional[int] = None,
    related_datasets: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Синхронизировать все дела с bankrot.gov.by в БД и файл.

    Args:
        db:           SQLAlchemy-сессия.
        page_size:    размер страницы пагинации (по умолчанию из конфига).
        delay:        пауза между страницами (сек).
        detail_delay: пауза между запросами detail/judgements (сек).
        output_dir:   директория для JSONL-файла.
        save_every:   flush в БД каждые N дел.
        token:        Bearer-токен (переопределяет BANKROT_API_TOKEN).
        filters:      фильтры для POST /cases (необязательно).
        fetch_related_data: загружать все публичные разделы карточки дела.
        related_page_size: размер страницы дочерних разделов.
        related_max_pages: защита от бесконечной пагинации.
        related_datasets: ограничить загрузку указанными именами наборов.

    Returns:
        dict со счётчиками: processed, failed, upserted, no_unp.

    Raises:
        Exception: при неожиданной ошибке (sync run помечается 'failed').
    """
    # --- Defaults from config ---
    page_size    = page_size    or settings.BANKROT_PAGE_SIZE
    delay        = delay        if delay        is not None else settings.BANKROT_PAGE_DELAY_SECONDS
    detail_delay = detail_delay if detail_delay is not None else settings.BANKROT_DETAIL_DELAY_SECONDS
    output_dir   = output_dir   or settings.BANKROT_OUTPUT_DIR
    save_every   = save_every   or settings.BANKROT_SAVE_EVERY
    fetch_related_data = (
        settings.BANKROT_FETCH_RELATED_DATA
        if fetch_related_data is None
        else fetch_related_data
    )
    related_page_size = related_page_size or settings.BANKROT_RELATED_PAGE_SIZE
    related_max_pages = related_max_pages or settings.BANKROT_RELATED_MAX_PAGES
    if related_datasets is None and settings.BANKROT_RELATED_DATASETS.strip():
        related_datasets = [
            item.strip()
            for item in settings.BANKROT_RELATED_DATASETS.split(",")
            if item.strip()
        ]
    selected_datasets = set(related_datasets) if related_datasets else None
    manager_data_cache: Dict[int, Dict[str, Dict[str, Any]]] = {}
    debtor_data_cache: Dict[int, Dict[str, Dict[str, Any]]] = {}
    sync_started_monotonic = time.monotonic()

    # --- Create sync run ---
    sync_run = BankrotSyncRun(status="running")
    db.add(sync_run)
    db.commit()
    db.refresh(sync_run)
    run_id = sync_run.id
    logger.info("Bankrot sync started: run_id=%d", run_id)

    # --- Prepare output paths ---
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    tmp_path   = out_dir / f"bankrot_cases_{run_id}_{ts}.jsonl.tmp"
    final_path = out_dir / f"bankrot_cases_{run_id}_{ts}.jsonl"

    stats: Dict[str, Any] = {
        "processed": 0,
        "failed":    0,
        "upserted":  0,
        "no_unp":    0,
        "with_unp":  0,
        "active_cases": 0,
        "closed_cases": 0,
        "unknown_status_cases": 0,
        "datasets_fetched": 0,
        "datasets_failed": 0,
    }

    def refresh_summary_stats() -> None:
        total_datasets = stats["datasets_fetched"] + stats["datasets_failed"]
        stats["total_cases"] = stats["processed"] + stats["failed"]
        stats["unique_debtors"] = len(debtor_data_cache)
        stats["unique_managers"] = len(manager_data_cache)
        stats["unp_coverage_pct"] = round(
            stats["with_unp"] * 100 / stats["processed"], 2
        ) if stats["processed"] else 0.0
        stats["dataset_success_pct"] = round(
            stats["datasets_fetched"] * 100 / total_datasets, 2
        ) if total_datasets else 100.0
        stats["duration_seconds"] = round(
            max(0.0, time.monotonic() - sync_started_monotonic), 2
        )

    pending: List[Dict] = []
    pending_datasets: List[Dict[str, Any]] = []

    try:
        with BankrotClient(token=token) as client, \
             open(tmp_path, "w", encoding="utf-8") as fout:

            for list_item in client.iter_all_cases(
                page_size=page_size,
                filters=filters,
                delay=delay,
            ):
                case_id: Any = list_item.get("id")
                if not case_id:
                    logger.warning(
                        "Bankrot: list item has no 'id' field — skipping: %s",
                        str(list_item)[:200],
                    )
                    stats["failed"] += 1
                    continue

                try:
                    case_id = int(case_id)
                except (ValueError, TypeError):
                    logger.warning("Bankrot: non-integer case id=%r — skipping", case_id)
                    stats["failed"] += 1
                    continue

                # ----- Fetch detail -----
                detail_data: Optional[Dict] = None
                errors: List[str] = []
                try:
                    detail_data = client.get_case_detail(case_id)
                except BankrotAPIError as exc:
                    logger.warning(
                        "Bankrot: detail error case_id=%d: %s", case_id, exc
                    )
                    errors.append(f"detail: {exc}")
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Bankrot: unexpected detail error case_id=%d: %s",
                        case_id, exc,
                    )
                    errors.append(f"detail: {exc}")

                if detail_delay > 0:
                    time.sleep(detail_delay)

                # ----- Fetch all public related sections -----
                related_data: Dict[str, Dict[str, Any]] = {}
                if fetch_related_data:
                    related_data = client.get_case_related_data(
                        case_id,
                        dataset_names=selected_datasets,
                        page_size=related_page_size,
                        max_pages=related_max_pages,
                        delay=detail_delay,
                    )
                    debtor_id = extract_debtor_id(list_item, detail_data)
                    if debtor_id is not None:
                        if debtor_id not in debtor_data_cache:
                            debtor_name = extract_debtor_name(list_item, detail_data)
                            debtor_data_cache[debtor_id] = client.get_debtor_related_data(
                                debtor_id,
                                debtor_name=debtor_name,
                                dataset_names=selected_datasets,
                                page_size=related_page_size,
                                max_pages=related_max_pages,
                            )
                        related_data.update(debtor_data_cache[debtor_id])

                    manager_id = extract_manager_id(list_item, detail_data)
                    if manager_id is not None:
                        if manager_id not in manager_data_cache:
                            manager_data_cache[manager_id] = client.get_manager_related_data(
                                manager_id,
                                dataset_names=selected_datasets,
                            )
                        related_data.update(manager_data_cache[manager_id])
                    now = datetime.utcnow()
                    for dataset_type, dataset in related_data.items():
                        payload = dataset.get("payload")
                        dataset_error = dataset.get("fetch_error")
                        pending_datasets.append(
                            {
                                "case_id": case_id,
                                "dataset_type": dataset_type,
                                "endpoint": dataset["endpoint"],
                                "http_method": dataset["http_method"],
                                "payload": payload,
                                "fetch_error": dataset_error,
                                "fetched_at": now if payload is not None else None,
                                "updated_at": now,
                            }
                        )
                        if dataset_error:
                            errors.append(f"{dataset_type}: {dataset_error}")
                            stats["datasets_failed"] += 1
                        else:
                            stats["datasets_fetched"] += 1

                # ----- Fetch judgements -----
                judgements_data: Optional[Dict] = None
                try:
                    judgements_data = client.get_case_judgements_group(case_id)
                except BankrotAPIError as exc:
                    logger.warning(
                        "Bankrot: judgements error case_id=%d: %s", case_id, exc
                    )
                    errors.append(f"judgements: {exc}")
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Bankrot: unexpected judgements error case_id=%d: %s",
                        case_id, exc,
                    )
                    errors.append(f"judgements: {exc}")

                if detail_delay > 0:
                    time.sleep(detail_delay)

                # ----- UNP -----
                unp = extract_unp(list_item, detail_data)
                if unp is None:
                    stats["no_unp"] += 1
                    logger.warning(
                        "Bankrot: UNP not found for case_id=%d number=%s — saved with NULL unp",
                        case_id,
                        list_item.get("number") or "?",
                    )
                else:
                    stats["with_unp"] += 1

                case_status = _safe_int(
                    (detail_data or {}).get("status", list_item.get("status"))
                )
                if case_status == 1:
                    stats["active_cases"] += 1
                elif case_status == 0:
                    stats["closed_cases"] += 1
                else:
                    stats["unknown_status_cases"] += 1

                fetch_error = "; ".join(errors) if errors else None

                # ----- Build & buffer -----
                row = _build_row(
                    case_id=case_id,
                    list_data=list_item,
                    detail_data=detail_data,
                    judgements_group=judgements_data,
                    unp=unp,
                    fetch_error=fetch_error,
                )
                pending.append(row)
                stats["processed"] += 1

                # Write merged record to JSONL
                merged = {
                    "case_id":        case_id,
                    "list_data":      list_item,
                    "detail_data":    detail_data,
                    "judgements_group": judgements_data,
                    "related_data": related_data,
                }
                fout.write(
                    json.dumps(merged, ensure_ascii=False, default=str) + "\n"
                )

                # ----- Intermediate DB flush -----
                if len(pending) >= save_every:
                    logger.info(
                        "Bankrot: flushing %d cases to DB (total processed=%d)…",
                        len(pending), stats["processed"],
                    )
                    _upsert_cases(db, list(pending))
                    _upsert_case_datasets(db, list(pending_datasets))
                    stats["upserted"] += len(pending)
                    pending.clear()
                    pending_datasets.clear()

                    # Update progress in sync run
                    refresh_summary_stats()
                    db.query(BankrotSyncRun).filter_by(id=run_id).update({
                        "total_cases":     stats["total_cases"],
                        "processed_cases": stats["processed"],
                        "failed_cases":    stats["failed"],
                        "stats_json":      dict(stats),
                    })
                    db.commit()

        # --- Final flush ---
        if pending:
            logger.info("Bankrot: final flush of %d cases…", len(pending))
            _upsert_cases(db, list(pending))
            _upsert_case_datasets(db, list(pending_datasets))
            stats["upserted"] += len(pending)
            pending.clear()
            pending_datasets.clear()

        # --- Atomic rename tmp → final ---
        tmp_path.rename(final_path)
        logger.info("Bankrot: output saved to %s", final_path)

        # --- Mark done ---
        refresh_summary_stats()
        db.query(BankrotSyncRun).filter_by(id=run_id).update({
            "status":          "done",
            "finished_at":     datetime.utcnow(),
            "total_cases":     stats["total_cases"],
            "processed_cases": stats["processed"],
            "failed_cases":    stats["failed"],
            "output_file":     str(final_path),
            "stats_json":      stats,
        })
        db.commit()

        logger.info(
            "Bankrot sync complete: run_id=%d processed=%d failed=%d "
            "no_unp=%d upserted=%d",
            run_id,
            stats["processed"],
            stats["failed"],
            stats["no_unp"],
            stats["upserted"],
        )
        return stats

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Bankrot sync FAILED: run_id=%d error=%s\n%s",
            run_id, exc, traceback.format_exc(),
        )

        # Clean up tmp file
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass

        # Mark run as failed
        try:
            db.rollback()
            refresh_summary_stats()
            db.query(BankrotSyncRun).filter_by(id=run_id).update({
                "status":          "failed",
                "finished_at":     datetime.utcnow(),
                "total_cases":     stats["total_cases"],
                "processed_cases": stats["processed"],
                "failed_cases":    stats["failed"],
                "error":           str(exc),
                "stats_json":      stats,
            })
            db.commit()
        except Exception as db_exc:  # noqa: BLE001
            logger.error(
                "Bankrot: failed to persist error state for run_id=%d: %s",
                run_id, db_exc,
            )

        raise
