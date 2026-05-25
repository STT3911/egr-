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

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.core.logger import get_logger
from app.database.models import BankrotCase, BankrotSyncRun
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
        _dig(primary, "managerModel", "fullName")
        or _dig(primary, "managerModel", "name")
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
            _dig(primary, "managerModel", "id")
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

def _upsert_cases(db: Session, rows: List[Dict[str, Any]]) -> None:
    """Bulk INSERT … ON CONFLICT (case_id) DO UPDATE для bankrot_cases.

    Обновляет все колонки кроме case_id и created_at.
    """
    if not rows:
        return

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

    stats: Dict[str, int] = {
        "processed": 0,
        "failed":    0,
        "upserted":  0,
        "no_unp":    0,
    }

    pending: List[Dict] = []

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
                    _upsert_cases(db, pending)
                    stats["upserted"] += len(pending)
                    pending.clear()

                    # Update progress in sync run
                    db.query(BankrotSyncRun).filter_by(id=run_id).update({
                        "processed_cases": stats["processed"],
                        "failed_cases":    stats["failed"],
                    })
                    db.commit()

        # --- Final flush ---
        if pending:
            logger.info("Bankrot: final flush of %d cases…", len(pending))
            _upsert_cases(db, pending)
            stats["upserted"] += len(pending)
            pending.clear()

        # --- Atomic rename tmp → final ---
        tmp_path.rename(final_path)
        logger.info("Bankrot: output saved to %s", final_path)

        # --- Mark done ---
        db.query(BankrotSyncRun).filter_by(id=run_id).update({
            "status":          "done",
            "finished_at":     datetime.utcnow(),
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
            db.query(BankrotSyncRun).filter_by(id=run_id).update({
                "status":          "failed",
                "finished_at":     datetime.utcnow(),
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
