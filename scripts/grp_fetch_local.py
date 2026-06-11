#!/usr/bin/env python3
"""
Локальный массовый забор ГРП (grp.nalog.gov.by) → JSONL.

Запускается на ЛОКАЛЬНОЙ машине, чтобы не грузить прод-сервер.
Резюмируемый: повторный запуск дозабирает только то, чего ещё нет в выходном файле.

Зависимость: httpx  (pip install httpx)

  python scripts/grp_fetch_local.py grp_pending_unps.txt grp_data.jsonl --concurrency 20

Вход  (grp_pending_unps.txt): список УНП, по одному в строке (экспорт с сервера).
Выход (grp_data.jsonl): по строке на УНП —
  {"unp":123, "raw_json":{...}, "http_status":200}      — успех
  {"unp":123, "raw_json":{}, "http_status":404}         — нет в реестре
  {"unp":123, "error":"...", "http_status":429}         — ошибка
"""
import argparse
import asyncio
import json
import os
import sys

import httpx

URL = "http://grp.nalog.gov.by/api/grp-public/data"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


def _normalize(data):
    if isinstance(data, list):
        if not data:
            return {}
        return data[0] if isinstance(data[0], dict) else {"value": data[0]}
    if isinstance(data, dict):
        if not data:
            return {}
        for k in ("row", "ROW", "data", "DATA"):
            if isinstance(data.get(k), dict):
                return data[k]
        return data
    return {}


async def fetch_one(client, unp, sem, retries=5):
    params = {"unp": str(unp), "charset": "UTF-8", "type": "json"}
    delay = 1.0
    for _ in range(retries):
        async with sem:
            try:
                r = await client.get(URL, params=params, timeout=20)
            except Exception:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
                continue
        if r.status_code == 404:
            return {"unp": unp, "raw_json": {}, "http_status": 404}
        if r.status_code == 429:
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)
            continue
        if r.status_code >= 400:
            return {"unp": unp, "error": f"http {r.status_code}", "http_status": r.status_code}
        try:
            data = r.json()
        except Exception as e:
            return {"unp": unp, "error": f"non-json: {e}", "http_status": r.status_code}
        return {"unp": unp, "raw_json": _normalize(data), "http_status": r.status_code}
    return {"unp": unp, "error": "max_retries", "http_status": 429}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("unps", help="файл со списком УНП (по одному в строке)")
    ap.add_argument("out", help="выходной JSONL")
    ap.add_argument("--concurrency", type=int, default=20)
    args = ap.parse_args()

    done = set()
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(int(json.loads(line)["unp"]))
                except Exception:
                    pass

    todo = []
    with open(args.unps, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s.isdigit() and int(s) not in done:
                todo.append(int(s))

    print(f"to fetch: {len(todo)} (already done: {len(done)})", file=sys.stderr)
    sem = asyncio.Semaphore(args.concurrency)
    batch_n = args.concurrency * 5

    with open(args.out, "a", encoding="utf-8") as out:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            for i in range(0, len(todo), batch_n):
                batch = todo[i:i + batch_n]
                results = await asyncio.gather(*[fetch_one(client, u, sem) for u in batch])
                for res in results:
                    out.write(json.dumps(res, ensure_ascii=False) + "\n")
                out.flush()
                print(f"  {min(i + batch_n, len(todo))}/{len(todo)}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
