#!/usr/bin/env python3
"""Directed brute-force enumeration of taxpayers via ГРП.

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
from typing import List, Set

from pathlib import Path

import httpx
from sqlalchemy import text
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

logger = get_logger("unp_enumerate")

CHECKPOINT_PATH = os.path.join("data", "unp_enumerate_checkpoint.json")


def load_known_unps(known_tables: List[str]) -> Set[int]:
    """Множество уже известных УНП (int) из перечисленных таблиц."""
    known: Set[int] = set()
    db = SessionLocal()
    try:
        for tbl in known_tables:
            try:
                rows = db.execute(text(f"SELECT unp FROM {tbl} WHERE unp IS NOT NULL"))
                for (unp,) in rows:
                    known.add(int(unp))
                logger.info("known: загружено из %s (итого %d)", tbl, len(known))
            except Exception as e:  # таблицы может не быть — пропускаем
                logger.warning("known: пропуск %s: %s", tbl, e)
                db.rollback()
    finally:
        db.close()
    return known


def save_checkpoint(region: int, seq: int, found: int) -> None:
    try:
        os.makedirs(os.path.dirname(CHECKPOINT_PATH), exist_ok=True)
        with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
            json.dump({"region": region, "seq": seq, "found": found, "ts": time.time()}, f)
    except Exception as e:
        logger.warning("checkpoint: не удалось записать: %s", e)


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


async def fetch_one(client: GRPClient, unp: str, max_retries: int, base_delay: float, cooldown: float) -> dict:
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


def is_hit(payload: dict) -> bool:
    """ГРП вернул реальную запись (а не пусто/404)."""
    if not payload:
        return False
    # ключи плательщика: vunp/VUNP/vnaimp ...
    keys = {k.lower() for k in payload.keys()}
    return bool(keys & {"vunp", "vnaimp", "vnaimk"})


async def run(args) -> None:
    regions = [int(x) for x in args.regions.split(",") if x.strip()]
    known = load_known_unps(args.known_tables.split(","))
    logger.info("Известных УНП в БД: %d", len(known))

    # резюме из чекпойнта: пропускаем уже пройденные регионы и стартуем с seq
    resume_region, resume_seq = None, None
    if args.resume:
        try:
            with open(CHECKPOINT_PATH, encoding="utf-8") as f:
                cp = json.load(f)
            resume_region, resume_seq = cp.get("region"), cp.get("seq")
            logger.info("resume: продолжаю с региона %s, seq %s", resume_region, resume_seq)
        except Exception as e:
            logger.warning("resume: чекпойнт не прочитан (%s), старт с начала", e)

    client = GRPClient()
    found = 0
    queried = 0
    last_logged = 0
    pending: list = []  # (unp_int, raw_json)
    try:
        for region in regions:
            if resume_region is not None and region < resume_region:
                continue
            empty_run = 0
            seq_start = args.seq_start
            if resume_region is not None and region == resume_region and resume_seq:
                seq_start = int(resume_seq)
            seq = seq_start
            while seq <= args.seq_end:
                # собрать батч НЕизвестных кандидатов (с сохранением порядка),
                # известные по пути считаем «существует» и сбрасываем empty_run
                batch: list = []
                while seq <= args.seq_end and len(batch) < args.concurrency:
                    unp = build_unp(region, seq)
                    seq += 1
                    if unp is None:
                        continue
                    if int(unp) in known:
                        empty_run = 0
                        continue
                    batch.append(unp)
                if not batch:
                    break

                results = await asyncio.gather(*[
                    fetch_one(client, u, args.max_retries, args.base_delay, args.cooldown)
                    for u in batch
                ])
                queried += len(batch)

                stop_region = False
                for u, payload in zip(batch, results):
                    if is_hit(payload):
                        pending.append((int(u), payload))
                        known.add(int(u))
                        found += 1
                        empty_run = 0
                        logger.info("HIT %s  %s", u, payload.get("vnaimp") or payload.get("VNAIMP") or "")
                    else:
                        empty_run += 1
                        if empty_run >= args.empty_stop:
                            stop_region = True

                if len(pending) >= args.flush_every:
                    upsert_hits(pending)
                    pending.clear()
                    save_checkpoint(region, seq, found)

                if queried - last_logged >= args.progress_every:
                    last_logged = queried
                    logger.info("регион %d seq~%d | запросов=%d найдено=%d пустых_подряд=%d",
                                region, seq, queried, found, empty_run)
                    save_checkpoint(region, seq, found)

                # вежливая пауза между батчами
                await asyncio.sleep(args.delay)

                if stop_region:
                    logger.info("регион %d: %d пустых подряд — стоп (фронтир выдачи)", region, args.empty_stop)
                    break

            upsert_hits(pending)
            pending.clear()
            save_checkpoint(region, seq, found)
    finally:
        upsert_hits(pending)
        await client.close()

    logger.info("ГОТОВО. Запросов к ГРП: %d, найдено новых: %d", queried, found)


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Directed brute-force УНП через ГРП")
    p.add_argument("--regions", default="1,2,3,4,5,6,7", help="первые знаки УНП (коды регионов) через запятую")
    p.add_argument("--seq-start", type=int, default=0, help="начальный порядковый номер (знаки 2-8)")
    p.add_argument("--seq-end", type=int, default=SEQ_MAX, help="конечный порядковый номер")
    p.add_argument("--empty-stop", type=int, default=20000, help="стоп по региону после N пустых подряд")
    p.add_argument("--concurrency", type=int, default=settings.GRP_FETCH_CONCURRENCY, help="одновременных запросов")
    p.add_argument("--delay", type=float, default=settings.GRP_FETCH_SUCCESS_DELAY_SECONDS, help="пауза между батчами, сек")
    p.add_argument("--max-retries", type=int, default=settings.GRP_FETCH_MAX_RETRIES)
    p.add_argument("--base-delay", type=float, default=settings.GRP_FETCH_RETRY_BASE_DELAY_SECONDS)
    p.add_argument("--cooldown", type=float, default=settings.GRP_FETCH_RETRY_COOLDOWN_MINUTES * 60.0,
                   help="пауза при 429, сек")
    p.add_argument("--flush-every", type=int, default=50, help="через сколько найденных писать в БД")
    p.add_argument("--progress-every", type=int, default=1000, help="лог прогресса каждые N запросов")
    p.add_argument("--known-tables", default="egr_raw_company_data,grp_raw_data,grp_taxpayer_data",
                   help="таблицы с известными УНП для дедупликации (через запятую)")
    p.add_argument("--resume", action="store_true",
                   help="продолжить с последнего чекпойнта (data/unp_enumerate_checkpoint.json)")
    return p


def main():
    args = build_argparser().parse_args()
    print("=" * 80)
    print("  НАПРАВЛЕННЫЙ ПЕРЕБОР УНП ЧЕРЕЗ ГРП")
    print("=" * 80)
    print(f"  регионы={args.regions}  seq=[{args.seq_start}..{args.seq_end}]")
    print(f"  concurrency={args.concurrency}  delay={args.delay}s  empty-stop={args.empty_stop}")
    print(f"  ⚠️  ГРП rate limit жёсткий — идём медленно. Ctrl+C для остановки.")
    print("=" * 80)
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nОстановлено пользователем. Прогресс во flush уже в БД.")
        sys.exit(130)


if __name__ == "__main__":
    main()
