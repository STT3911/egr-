#!/usr/bin/env python3
"""Directed checksum-valid UNP frontier checks through EGR and GRP.

Идея (см. app/services/unp_enum.py):
  1. Генерируем валидные УНП по формуле (контрольная цифра), а не все 10^9.
  2. Дедупим против уже известных УНП в БД (ЕГР + ГРП) — чтобы НЕ слать в ГРП то,
     что уже есть.
  3. Идём по порядковым номерам ВОЗРАСТАЮЩЕ внутри региона. Известные УНП считаем
     «существует» и сбрасываем счётчик пустых; для неизвестных дёргаем ГРП.
     После N подряд пустых в регионе — стоп (вышли за фронтир выдачи номеров).
  4. Найденное кладём в grp_raw_data (parsed=False) — штатная задача grp_process_raw
     распарсит в grp_taxpayer_data.

ГРП имеет жёсткий rate limit — по умолчанию малый concurrency и пауза между
запросами (берём из настроек GRP_FETCH_*). Запуск из корня проекта:

  python scripts/unp_enumerate.py --regions 1,2,3,4,5,6,7 --seq-end 1500000 \
      --empty-stop 20000 --concurrency 2 --delay 2.0
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pathlib import Path

import httpx
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.core.config import settings
from app.core.logger import get_logger
from app.database.models import GrpRawData
from app.services.grp_client import GRPClient
from app.services.unp_enum import build_unp, SEQ_MAX
from app.services.unp_probe import DualSourceProbe
from app.services.unp_scan_registry import (
    claim_next_range_scan,
    complete_range_scan,
    ensure_range_scan_cycle,
    get_latest_issuance_range,
    get_range_scan_cycle_status,
    get_registry_status,
    plan_candidates,
    prepare_scan_registry,
    record_probe_results,
    update_range_scan_progress,
)

logger = get_logger("unp_enumerate")

CHECKPOINT_PATH = str(ROOT / "data" / "unp_enumerate_checkpoint.json")


def find_latest_known_seq(region: int, known_tables: list[str]) -> int | None:
    """Return the highest known seven-digit sequence for one region."""
    lower_unp = region * 100_000_000
    upper_unp = (region + 1) * 100_000_000
    latest_unp: int | None = None
    source_filters = {
        "egr_companies": "TRUE",
        "egr_raw_company_data": (
            "(data IS NOT NULL OR base_info IS NOT NULL) "
            "AND last_error IS NULL"
        ),
        "grp_raw_data": (
            "http_status = 200 "
            "AND raw_json IS NOT NULL "
            "AND raw_json <> '{}'::jsonb"
        ),
        "grp_taxpayer_data": "TRUE",
    }
    db = SessionLocal()
    try:
        for table_name in known_tables:
            source_filter = source_filters.get(table_name)
            if source_filter is None:
                logger.warning(
                    "frontier lookup skipped unsupported table %s",
                    table_name,
                )
                continue
            try:
                value = db.execute(
                    text(
                        f"SELECT MAX(unp) FROM {table_name} "
                        "WHERE unp >= :lower_unp AND unp < :upper_unp "
                        f"AND ({source_filter})"
                    ),
                    {"lower_unp": lower_unp, "upper_unp": upper_unp},
                ).scalar()
                if value is not None:
                    candidate = int(value)
                    latest_unp = (
                        candidate
                        if latest_unp is None
                        else max(latest_unp, candidate)
                    )
            except Exception as exc:
                logger.warning("frontier lookup skipped %s: %s", table_name, exc)
                db.rollback()
    finally:
        db.close()

    if latest_unp is None:
        return None
    return (latest_unp // 10) % 10_000_000


def find_known_unps(unps: list[int], known_tables: list[str]) -> set[int]:
    """Return known UNPs without loading entire database tables into memory."""
    if not unps:
        return set()

    known: set[int] = set()
    db = SessionLocal()
    try:
        for table_name in known_tables:
            try:
                stmt = text(
                    f"SELECT unp FROM {table_name} WHERE unp IN :unps"
                ).bindparams(bindparam("unps", expanding=True))
                rows = db.execute(stmt, {"unps": unps})
                for (unp,) in rows:
                    known.add(int(unp))
            except Exception as exc:
                logger.warning("known lookup skipped %s: %s", table_name, exc)
                db.rollback()
    finally:
        db.close()
    return known


def find_source_presence(unps: list[int]) -> tuple[set[int], set[int]]:
    """Return UNPs with successfully persisted EGR and GRP source data."""
    if not unps:
        return set(), set()

    egr_present: set[int] = set()
    grp_present: set[int] = set()
    checks = (
        (
            egr_present,
            """
            SELECT unp FROM egr_raw_company_data
            WHERE unp IN :unps
              AND (data IS NOT NULL OR base_info IS NOT NULL)
              AND processed_at IS NOT NULL
              AND last_error IS NULL
            """,
        ),
        (
            egr_present,
            """
            SELECT unp FROM egr_companies
            WHERE unp IN :unps AND source = 'egr'
            """,
        ),
        (
            grp_present,
            "SELECT unp FROM grp_taxpayer_data WHERE unp IN :unps",
        ),
        (
            grp_present,
            """
            SELECT unp FROM grp_raw_data
            WHERE unp IN :unps
              AND http_status = 200
              AND raw_json <> '{}'::jsonb
            """,
        ),
        (
            grp_present,
            """
            SELECT unp FROM egr_companies
            WHERE unp IN :unps AND source = 'grp'
            """,
        ),
    )
    db = SessionLocal()
    try:
        for target, sql in checks:
            try:
                rows = db.execute(
                    text(sql).bindparams(bindparam("unps", expanding=True)),
                    {"unps": unps},
                )
                target.update(int(unp) for (unp,) in rows)
            except Exception as exc:
                logger.warning("source presence lookup failed: %s", exc)
                db.rollback()
    finally:
        db.close()
    return egr_present, grp_present


def _save_checkpoint_legacy(region: int, seq: int, found: int) -> None:
    try:
        os.makedirs(os.path.dirname(CHECKPOINT_PATH), exist_ok=True)
        with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
            json.dump({"region": region, "seq": seq, "found": found, "ts": time.time()}, f)
    except Exception as e:
        logger.warning("checkpoint: не удалось записать: %s", e)


def _next_candidate_unp(region: int, seq: int) -> str | None:
    candidate_seq = max(0, seq)
    while candidate_seq <= SEQ_MAX:
        unp = build_unp(region, candidate_seq)
        if unp is not None:
            return unp
        candidate_seq += 1
    return None


def save_checkpoint(
    region: int,
    seq: int,
    found: int,
    *,
    queried: int = 0,
    misses: int = 0,
    errors: int = 0,
    last_unp: str | None = None,
    extra: dict | None = None,
) -> None:
    try:
        os.makedirs(os.path.dirname(CHECKPOINT_PATH), exist_ok=True)
        payload = {
            "region": region,
            "seq": seq,
            "last_unp": last_unp,
            "next_unp": _next_candidate_unp(region, seq),
            "queried": queried,
            "found": found,
            "misses": misses,
            "errors": errors,
            "pid": os.getpid(),
            "ts": time.time(),
        }
        if extra:
            payload.update(extra)
        tmp_path = f"{CHECKPOINT_PATH}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as checkpoint_file:
            json.dump(payload, checkpoint_file, ensure_ascii=False, indent=2)
        os.replace(tmp_path, CHECKPOINT_PATH)
    except Exception as exc:
        logger.warning("checkpoint write failed: %s", exc)


def upsert_hits(rows: list) -> None:
    """rows: list of (unp:int, raw_json:dict). Bulk upsert в grp_raw_data."""
    if not rows:
        return
    db = SessionLocal()
    try:
        values = [
            {"unp": unp, "raw_json": raw, "http_status": 200, "parsed": False}
            for unp, raw in rows
        ]
        stmt = pg_insert(GrpRawData).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[GrpRawData.unp],
            set_={
                "raw_json": stmt.excluded.raw_json,
                "http_status": stmt.excluded.http_status,
                "parsed": False,
                "parsed_at": None,
            },
        )
        db.execute(stmt)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("upsert_hits failed: %s", e)
        raise
    finally:
        db.close()


async def _fetch_one_legacy(client: GRPClient, unp: str, max_retries: int, base_delay: float, cooldown: float) -> dict:
    """Запрос к ГРП с ретраями. Возвращает dict (пустой если не найден)."""
    attempt = 0
    while True:
        try:
            return await client.get_taxpayer(int(unp))
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else None
            # 4xx (кроме 429) = УНП не существует/невалиден → сразу пусто, БЕЗ ретраев.
            # ГРП на несуществующий номер отдаёт 400 — а таких большинство, поэтому
            # ретраить их нельзя (сожжёт rate-limit вхолостую).
            if status is not None and 400 <= status < 500 and status != 429:
                return {}
            attempt += 1
            if status == 429:
                wait = cooldown
                logger.warning("429 на УНП %s — пауза %.0fs (попытка %d)", unp, wait, attempt)
            else:
                wait = base_delay * attempt
            if attempt > max_retries:
                logger.error("УНП %s: исчерпаны ретраи (%s)", unp, status)
                return {}
            await asyncio.sleep(wait)
        except (httpx.HTTPError, ValueError) as e:
            attempt += 1
            if attempt > max_retries:
                logger.error("УНП %s: ошибка после ретраев: %s", unp, e)
                return {}
            await asyncio.sleep(base_delay * attempt)


@dataclass(frozen=True)
class FetchResult:
    outcome: Literal["hit", "miss", "error"]
    payload: dict | None = None
    status_code: int | None = None
    error: str | None = None


async def fetch_one(
    client: GRPClient,
    unp: str,
    max_retries: int,
    base_delay: float,
    cooldown: float,
) -> FetchResult:
    """Fetch one UNP without confusing a transport failure with a confirmed miss."""
    attempt = 0
    while True:
        try:
            payload = await client.get_taxpayer(int(unp))
            if not payload:
                return FetchResult(outcome="miss", status_code=404)
            if is_hit(payload):
                return FetchResult(outcome="hit", payload=payload, status_code=200)
            return FetchResult(
                outcome="error",
                payload=payload,
                status_code=200,
                error="GRP returned an unexpected payload shape",
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status is not None and 400 <= status < 500 and status != 429:
                return FetchResult(outcome="miss", status_code=status)

            attempt += 1
            wait = cooldown if status == 429 else base_delay * attempt
            if attempt > max_retries:
                return FetchResult(
                    outcome="error",
                    status_code=status,
                    error=str(exc),
                )
            logger.warning(
                "GRP retry UNP %s, HTTP %s, attempt %s/%s in %.1fs",
                unp,
                status,
                attempt,
                max_retries,
                wait,
            )
            await asyncio.sleep(wait)
        except (httpx.HTTPError, ValueError) as exc:
            attempt += 1
            if attempt > max_retries:
                return FetchResult(outcome="error", error=str(exc))
            await asyncio.sleep(base_delay * attempt)


def is_hit(payload: dict) -> bool:
    """ГРП вернул реальную запись (а не пусто/404)."""
    if not payload:
        return False
    # ключи плательщика: vunp/VUNP/vnaimp ...
    keys = {k.lower() for k in payload.keys()}
    return bool(keys & {"vunp", "vnaimp", "vnaimk"})


def _summarize_range_candidates(
    candidates: list[str],
    *,
    egr_present: set[int],
    grp_present: set[int],
    results_by_unp: dict[str, object],
) -> tuple[int, int, int]:
    found_count = 0
    not_found_count = 0
    error_count = 0
    for unp in candidates:
        numeric_unp = int(unp)
        if numeric_unp in egr_present and numeric_unp in grp_present:
            found_count += 1
            continue
        result = results_by_unp.get(unp)
        if result is None:
            continue
        if result.outcome == "hit":
            found_count += 1
        elif result.outcome == "miss":
            not_found_count += 1
        else:
            error_count += 1
    return found_count, not_found_count, error_count


async def _run_range_scan_cycle(
    args,
    *,
    regions: list[int],
    stop_event=None,
) -> Literal["completed", "retry", "stopped"]:
    cycle_status = ensure_range_scan_cycle(
        regions=regions,
        seq_start=args.seq_start,
        seq_end=args.seq_end,
        gap_limit=args.range_gap,
        frontier_backtrack=args.frontier_backtrack,
        frontier_lookahead=args.frontier_lookahead,
    )
    cycle_number = int(cycle_status["cycle_number"])
    logger.info(
        "UNP range cycle %d: ranges=%d completed=%d pending=%d checked=%d",
        cycle_number,
        cycle_status["ranges"],
        cycle_status["completed_ranges"],
        cycle_status["pending_ranges"],
        cycle_status["checked"],
    )

    probe = DualSourceProbe()
    queried = 0
    found = 0
    misses = 0
    errors = 0
    last_unp: str | None = None
    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                return "stopped"

            range_scan = claim_next_range_scan(cycle_number)
            if range_scan is None:
                completed_status = get_range_scan_cycle_status(cycle_number)
                logger.info(
                    "UNP range cycle %d completed: ranges=%d checked=%d "
                    "found=%d not_found=%d errors=%d",
                    cycle_number,
                    completed_status["ranges"],
                    completed_status["checked"],
                    completed_status["found"],
                    completed_status["not_found"],
                    completed_status["errors"],
                )
                return "completed"

            logger.info(
                "UNP range cycle %d range=%d region=%d "
                "source=%d-%d scan=%d-%d resume=%d",
                cycle_number,
                range_scan.id,
                range_scan.region,
                range_scan.source_seq_start,
                range_scan.source_seq_end,
                range_scan.scan_start,
                range_scan.scan_end,
                range_scan.next_sequence,
            )
            sequence = max(range_scan.scan_start, range_scan.next_sequence)

            while sequence <= range_scan.scan_end:
                if stop_event is not None and stop_event.is_set():
                    save_checkpoint(
                        range_scan.region,
                        sequence,
                        found,
                        queried=queried,
                        misses=misses,
                        errors=errors,
                        last_unp=last_unp,
                        extra={
                            "cycle_number": cycle_number,
                            "range_scan_id": range_scan.id,
                        },
                    )
                    return "stopped"

                candidates: list[str] = []
                while (
                    sequence <= range_scan.scan_end
                    and len(candidates) < args.candidate_batch
                ):
                    unp = build_unp(range_scan.region, sequence)
                    sequence += 1
                    if unp is not None:
                        candidates.append(unp)
                if not candidates:
                    break

                numeric_candidates = [int(unp) for unp in candidates]
                egr_present, grp_present = find_source_presence(
                    numeric_candidates
                )
                plan_candidates(
                    candidates,
                    egr_present=egr_present,
                    grp_present=grp_present,
                )
                probe_candidates = [
                    unp
                    for unp in candidates
                    if int(unp) not in egr_present
                    or int(unp) not in grp_present
                ]
                results_by_unp: dict[str, object] = {}
                failed_unps: list[str] = []

                for offset in range(
                    0,
                    len(probe_candidates),
                    args.concurrency,
                ):
                    chunk = probe_candidates[
                        offset : offset + args.concurrency
                    ]
                    results = await asyncio.gather(
                        *[
                            probe.probe(
                                unp,
                                need_egr=int(unp) not in egr_present,
                                need_grp=int(unp) not in grp_present,
                                max_retries=args.max_retries,
                                retry_delay=args.base_delay,
                                cooldown=args.cooldown,
                            )
                            for unp in chunk
                        ]
                    )
                    record_probe_results(results)
                    queried += len(results)
                    for result in results:
                        results_by_unp[result.unp] = result
                        last_unp = result.unp
                        if result.outcome == "hit":
                            found += result.new_found
                            logger.info(
                                "HIT %s | EGR=%s GRP=%s",
                                result.unp,
                                result.egr.status,
                                result.grp.status,
                            )
                        elif result.outcome == "miss":
                            misses += 1
                        else:
                            errors += 1
                            if result.persist_errors:
                                failed_unps.append(result.unp)
                            logger.warning(
                                "UNP %s was not checked in both sources: "
                                "EGR=%s GRP=%s, %s",
                                result.unp,
                                result.egr.status,
                                result.grp.status,
                                result.error or "unknown source error",
                            )

                    if failed_unps:
                        break
                    if args.delay > 0:
                        await asyncio.sleep(args.delay)

                if failed_unps:
                    retry_sequence = min(
                        int(unp[1:8]) for unp in failed_unps
                    )
                    completed_candidates = [
                        unp
                        for unp in candidates
                        if int(unp[1:8]) < retry_sequence
                    ]
                    range_found, range_misses, range_errors = (
                        _summarize_range_candidates(
                            completed_candidates,
                            egr_present=egr_present,
                            grp_present=grp_present,
                            results_by_unp=results_by_unp,
                        )
                    )
                    update_range_scan_progress(
                        range_scan.id,
                        next_sequence=retry_sequence,
                        first_checked_unp=(
                            int(completed_candidates[0])
                            if completed_candidates
                            else None
                        ),
                        last_checked_unp=(
                            int(completed_candidates[-1])
                            if completed_candidates
                            else None
                        ),
                        checked_count=len(completed_candidates),
                        found_count=range_found,
                        not_found_count=range_misses,
                        error_count=range_errors + len(failed_unps),
                    )
                    save_checkpoint(
                        range_scan.region,
                        retry_sequence,
                        found,
                        queried=queried,
                        misses=misses,
                        errors=errors,
                        last_unp=last_unp,
                        extra={
                            "cycle_number": cycle_number,
                            "range_scan_id": range_scan.id,
                        },
                    )
                    logger.error(
                        "Range scan paused without skipping data; "
                        "cycle=%d range=%d next=%s",
                        cycle_number,
                        range_scan.id,
                        _next_candidate_unp(
                            range_scan.region,
                            retry_sequence,
                        ),
                    )
                    return "retry"

                range_found, range_misses, range_errors = (
                    _summarize_range_candidates(
                        candidates,
                        egr_present=egr_present,
                        grp_present=grp_present,
                        results_by_unp=results_by_unp,
                    )
                )
                update_range_scan_progress(
                    range_scan.id,
                    next_sequence=sequence,
                    first_checked_unp=int(candidates[0]),
                    last_checked_unp=int(candidates[-1]),
                    checked_count=len(candidates),
                    found_count=range_found,
                    not_found_count=range_misses,
                    error_count=range_errors,
                )
                last_unp = candidates[-1]
                save_checkpoint(
                    range_scan.region,
                    sequence,
                    found,
                    queried=queried,
                    misses=misses,
                    errors=errors,
                    last_unp=last_unp,
                    extra={
                        "cycle_number": cycle_number,
                        "range_scan_id": range_scan.id,
                    },
                )

            complete_range_scan(range_scan.id)
            logger.info(
                "UNP range completed: cycle=%d range=%d region=%d "
                "first_seq=%d last_seq=%d",
                cycle_number,
                range_scan.id,
                range_scan.region,
                range_scan.scan_start,
                range_scan.scan_end,
            )
    finally:
        await probe.close()


async def run(args, stop_event=None) -> Literal["completed", "retry", "stopped"]:
    if args.concurrency <= 0:
        raise ValueError("concurrency must be greater than zero")
    if args.candidate_batch <= 0:
        raise ValueError("candidate_batch must be greater than zero")
    regions = [int(x) for x in args.regions.split(",") if x.strip()]
    known_tables = [name.strip() for name in args.known_tables.split(",") if name.strip()]
    frontier_mode = args.scan_mode == "frontier"
    logger.info("Known UNPs will be checked in small DB batches: %s", known_tables)
    logger.info(
        "UNP scan mode=%s frontier_lookahead=%s frontier_backtrack=%s",
        args.scan_mode,
        args.frontier_lookahead,
        args.frontier_backtrack,
    )

    registry_status = prepare_scan_registry(
        gap_limit=args.range_gap,
        frontier_backtrack=args.frontier_backtrack,
        frontier_lookahead=args.frontier_lookahead,
        force=args.prepare_only,
        max_age_seconds=args.registry_refresh_interval,
    )
    logger.info(
        "UNP registry prepared: candidates=%s known=%s ranges=%s planned=%s",
        registry_status["candidates"],
        registry_status["known"],
        registry_status["ranges"],
        registry_status["planned_candidates"],
    )
    if args.prepare_only:
        print(json.dumps(registry_status, ensure_ascii=False, indent=2))
        return "completed"
    if frontier_mode:
        return await _run_range_scan_cycle(
            args,
            regions=regions,
            stop_event=stop_event,
        )

    # резюме из чекпойнта: пропускаем уже пройденные регионы и стартуем с seq
    resume_region, resume_seq = None, None
    checkpoint = {}
    if args.resume and not frontier_mode:
        try:
            with open(CHECKPOINT_PATH, encoding="utf-8-sig") as f:
                checkpoint = json.load(f)
            resume_region, resume_seq = checkpoint.get("region"), checkpoint.get("seq")
            logger.info("resume: продолжаю с региона %s, seq %s", resume_region, resume_seq)
        except Exception as e:
            logger.warning("resume: чекпойнт не прочитан (%s), старт с начала", e)

    probe = DualSourceProbe()
    found = int(checkpoint.get("found") or 0)
    queried = int(checkpoint.get("queried") or 0)
    misses = int(checkpoint.get("misses") or 0)
    errors = int(checkpoint.get("errors") or 0)
    last_logged = queried
    last_checkpointed = queried
    last_unp = checkpoint.get("last_unp")
    pending: list = []  # (unp_int, raw_json)
    waiting_for_resume_region = resume_region is not None
    if waiting_for_resume_region and resume_region not in regions:
        logger.warning(
            "resume region %s is not present in --regions=%s; starting from the beginning",
            resume_region,
            regions,
        )
        waiting_for_resume_region = False
        resume_region = None
        resume_seq = None
    try:
        for region in regions:
            if waiting_for_resume_region:
                if region != resume_region:
                    continue
                waiting_for_resume_region = False
            empty_run = 0
            seq_start = args.seq_start
            if frontier_mode:
                issuance_range = get_latest_issuance_range(region)
                latest_database_seq = find_latest_known_seq(region, known_tables)
                latest_known_seq = max(
                    [
                        value
                        for value in (
                            issuance_range.seq_end
                            if issuance_range is not None
                            else None,
                            latest_database_seq,
                        )
                        if value is not None
                    ],
                    default=None,
                )
                if (
                    issuance_range is not None
                    and latest_known_seq == issuance_range.seq_end
                ):
                    seq_start = max(args.seq_start, issuance_range.scan_start)
                elif latest_known_seq is not None:
                    seq_start = max(
                        args.seq_start,
                        latest_known_seq + 1 - args.frontier_backtrack,
                    )
                logger.info(
                    "region %d frontier: latest_known_seq=%s start_seq=%d lookahead=%d range=%s",
                    region,
                    latest_known_seq,
                    seq_start,
                    args.frontier_lookahead,
                    (
                        f"{issuance_range.seq_start}-{issuance_range.seq_end}"
                        if issuance_range is not None
                        else "fallback"
                    ),
                )
            elif resume_region is not None and region == resume_region and resume_seq is not None:
                seq_start = int(resume_seq)
            seq = seq_start
            empty_stop = (
                args.frontier_lookahead
                if frontier_mode
                else args.empty_stop
            )
            save_checkpoint(
                region,
                seq,
                found,
                queried=queried,
                misses=misses,
                errors=errors,
                last_unp=last_unp,
            )
            while seq <= args.seq_end:
                if stop_event is not None and stop_event.is_set():
                    upsert_hits(pending)
                    pending.clear()
                    save_checkpoint(
                        region,
                        seq,
                        found,
                        queried=queried,
                        misses=misses,
                        errors=errors,
                        last_unp=last_unp,
                    )
                    return "stopped"

                candidates: list[str] = []
                while seq <= args.seq_end and len(candidates) < args.concurrency:
                    unp = build_unp(region, seq)
                    seq += 1
                    if unp is None:
                        continue
                    candidates.append(unp)
                if not candidates:
                    break

                egr_present, grp_present = find_source_presence(
                    [int(unp) for unp in candidates],
                )
                plan_candidates(
                    candidates,
                    egr_present=egr_present,
                    grp_present=grp_present,
                )
                batch = [
                    unp
                    for unp in candidates
                    if int(unp) not in egr_present
                    or int(unp) not in grp_present
                ]

                results = await asyncio.gather(*[
                    probe.probe(
                        u,
                        need_egr=int(u) not in egr_present,
                        need_grp=int(u) not in grp_present,
                        max_retries=args.max_retries,
                        retry_delay=args.base_delay,
                        cooldown=args.cooldown,
                    )
                    for u in batch
                ])
                record_probe_results(results)
                queried += len(batch)

                failed_unps: list[str] = []
                results_by_unp = dict(zip(batch, results))
                for u in candidates:
                    last_unp = u
                    if int(u) in egr_present and int(u) in grp_present:
                        empty_run = 0
                        continue

                    result = results_by_unp[u]
                    if result.outcome == "hit":
                        found += result.new_found
                        empty_run = 0
                        logger.info(
                            "HIT %s | EGR=%s GRP=%s",
                            u,
                            result.egr.status,
                            result.grp.status,
                        )
                    elif result.outcome == "miss":
                        misses += 1
                        empty_run += 1
                    else:
                        errors += 1
                        if result.persist_errors:
                            failed_unps.append(u)
                        logger.warning(
                            "UNP %s was not checked in both sources: EGR=%s GRP=%s, %s",
                            u,
                            result.egr.status,
                            result.grp.status,
                            result.error or "unknown source error",
                        )

                if failed_unps:
                    retry_seq = min(int(unp[1:8]) for unp in failed_unps)
                    upsert_hits(pending)
                    pending.clear()
                    save_checkpoint(
                        region,
                        retry_seq,
                        found,
                        queried=queried,
                        misses=misses,
                        errors=errors,
                        last_unp=last_unp,
                    )
                    logger.error(
                        "Enumeration stopped without skipping data; rerun with --resume. Next UNP: %s",
                        _next_candidate_unp(region, retry_seq),
                    )
                    return "retry"

                if len(pending) >= args.flush_every:
                    upsert_hits(pending)
                    pending.clear()

                if queried - last_logged >= args.progress_every:
                    last_logged = queried
                    logger.info("регион %d seq~%d | запросов=%d найдено=%d пустых_подряд=%d",
                                region, seq, queried, found, empty_run)
                    upsert_hits(pending)
                    pending.clear()
                    save_checkpoint(
                        region,
                        seq,
                        found,
                        queried=queried,
                        misses=misses,
                        errors=errors,
                        last_unp=last_unp,
                    )

                if queried - last_checkpointed >= args.checkpoint_every:
                    last_checkpointed = queried
                    upsert_hits(pending)
                    pending.clear()
                    save_checkpoint(
                        region,
                        seq,
                        found,
                        queried=queried,
                        misses=misses,
                        errors=errors,
                        last_unp=last_unp,
                    )

                # вежливая пауза между батчами
                await asyncio.sleep(args.delay)

                if empty_stop > 0 and empty_run >= empty_stop:
                    logger.info(
                        "region %d: %d consecutive misses, frontier reached",
                        region,
                        empty_stop,
                    )
                    break

            upsert_hits(pending)
            pending.clear()
            save_checkpoint(
                region,
                seq,
                found,
                queried=queried,
                misses=misses,
                errors=errors,
                last_unp=last_unp,
            )
    finally:
        upsert_hits(pending)
        await probe.close()

    logger.info(
        "ГОТОВО. Проверено кандидатов через ЕГР/ГРП: %d, найдено новых: %d",
        queried,
        found,
    )
    return "completed"


def print_status() -> int:
    try:
        with open(CHECKPOINT_PATH, encoding="utf-8-sig") as checkpoint_file:
            checkpoint = json.load(checkpoint_file)
    except FileNotFoundError:
        print(f"Checkpoint not found: {CHECKPOINT_PATH}")
        return 1
    except Exception as exc:
        print(f"Cannot read checkpoint {CHECKPOINT_PATH}: {exc}")
        return 1

    updated_at = None
    age_seconds = None
    if checkpoint.get("ts"):
        updated_at = datetime.fromtimestamp(float(checkpoint["ts"])).astimezone()
        age_seconds = max(0, int(time.time() - float(checkpoint["ts"])))

    print(f"checkpoint: {CHECKPOINT_PATH}")
    print(f"updated_at: {updated_at.isoformat(timespec='seconds') if updated_at else '-'}")
    print(f"age_seconds: {age_seconds if age_seconds is not None else '-'}")
    print(f"pid: {checkpoint.get('pid', '-')}")
    print(f"region: {checkpoint.get('region', '-')}")
    print(f"last_unp: {checkpoint.get('last_unp', '-')}")
    print(f"next_unp: {checkpoint.get('next_unp', '-')}")
    print(f"next_seq: {checkpoint.get('seq', '-')}")
    print(f"queried: {checkpoint.get('queried', 0)}")
    print(f"found: {checkpoint.get('found', 0)}")
    print(f"misses: {checkpoint.get('misses', 0)}")
    print(f"errors: {checkpoint.get('errors', 0)}")
    try:
        registry_status = get_registry_status()
    except Exception as exc:
        print(f"registry_error: {type(exc).__name__}: {exc}")
    else:
        print(f"registry_candidates: {registry_status['candidates']}")
        print(f"registry_known: {registry_status['known']}")
        print(f"registry_pending: {registry_status['pending']}")
        print(f"registry_not_found: {registry_status['not_found']}")
        print(f"registry_partial: {registry_status['partial']}")
        print(f"registry_errors: {registry_status['errors']}")
        print(f"registry_ranges: {registry_status['ranges']}")
        print(
            "registry_latest_ranges: "
            + json.dumps(
                registry_status["latest_ranges"],
                ensure_ascii=False,
            )
        )
    return 0


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Directed brute-force УНП через ГРП")
    p.add_argument("--regions", default="1,2,3,4,5,6,7", help="первые знаки УНП (коды регионов) через запятую")
    p.add_argument("--seq-start", type=int, default=0, help="начальный порядковый номер (знаки 2-8)")
    p.add_argument("--seq-end", type=int, default=SEQ_MAX, help="конечный порядковый номер")
    p.add_argument(
        "--empty-stop",
        type=int,
        default=20000,
        help="стоп по региону после N пустых подряд; 0 отключает раннюю остановку",
    )
    p.add_argument("--concurrency", type=int, default=settings.GRP_FETCH_CONCURRENCY, help="одновременных запросов")
    p.add_argument(
        "--candidate-batch",
        type=int,
        default=500,
        help="сколько кандидатов диапазона сверять с БД одним блоком",
    )
    p.add_argument("--delay", type=float, default=settings.GRP_FETCH_SUCCESS_DELAY_SECONDS, help="пауза между батчами, сек")
    p.add_argument("--max-retries", type=int, default=settings.GRP_FETCH_MAX_RETRIES)
    p.add_argument("--base-delay", type=float, default=settings.GRP_FETCH_RETRY_BASE_DELAY_SECONDS)
    p.add_argument("--cooldown", type=float, default=settings.GRP_FETCH_RETRY_COOLDOWN_MINUTES * 60.0,
                   help="пауза при 429, сек")
    p.add_argument("--flush-every", type=int, default=50, help="через сколько найденных писать в БД")
    p.add_argument("--progress-every", type=int, default=1000, help="лог прогресса каждые N запросов")
    p.add_argument("--checkpoint-every", type=int, default=20,
                   help="update checkpoint after every N candidate checks")
    p.add_argument("--checkpoint-path", default=CHECKPOINT_PATH,
                   help="checkpoint file path (use a separate file for audit runs)")
    p.add_argument("--known-tables", default="egr_companies,egr_raw_company_data,grp_raw_data,grp_taxpayer_data",
                   help="таблицы с известными УНП для дедупликации (через запятую)")
    p.add_argument("--scan-mode", choices=("frontier", "full"), default="frontier",
                   help="frontier checks after the latest known regional UNP; full walks the configured range")
    p.add_argument("--frontier-lookahead", type=int, default=50,
                   help="stop a regional frontier after N consecutive confirmed misses")
    p.add_argument("--frontier-backtrack", type=int, default=50,
                   help="recheck this many sequence positions before the latest known regional UNP")
    p.add_argument("--range-gap", type=int, default=50,
                   help="split inferred issuance ranges when known sequence gaps exceed N")
    p.add_argument("--registry-refresh-interval", type=float, default=86400,
                   help="minimum seconds between full DB marking and range rebuilds")
    p.add_argument("--prepare-only", action="store_true",
                   help="populate candidate marks and issuance ranges without external API requests")
    p.add_argument("--registry-status", action="store_true",
                   help="show candidate and issuance range statistics from the database")
    p.add_argument("--resume", action="store_true",
                   help="продолжить с последнего чекпойнта (data/unp_enumerate_checkpoint.json)")
    p.add_argument("--status", action="store_true", help="show current checkpoint and exit")
    return p


def main():
    global CHECKPOINT_PATH
    args = build_argparser().parse_args()
    CHECKPOINT_PATH = os.path.abspath(args.checkpoint_path)
    if args.registry_status:
        print(json.dumps(get_registry_status(), ensure_ascii=False, indent=2))
        raise SystemExit(0)
    if args.status:
        raise SystemExit(print_status())
    print("=" * 80)
    print(
        "  ПОДГОТОВКА РЕЕСТРА КАНДИДАТОВ УНП"
        if args.prepare_only
        else "  НАПРАВЛЕННЫЙ ПЕРЕБОР УНП ЧЕРЕЗ ЕГР И ГРП"
    )
    print("=" * 80)
    print(f"  регионы={args.regions}  seq=[{args.seq_start}..{args.seq_end}]")
    print(f"  concurrency={args.concurrency}  delay={args.delay}s  empty-stop={args.empty_stop}")
    if not args.prepare_only:
        print("  ⚠️  Учитываем rate limit источников. Ctrl+C для остановки.")
    print("=" * 80)
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nОстановлено пользователем. Прогресс во flush уже в БД.")
        sys.exit(130)


if __name__ == "__main__":
    main()
