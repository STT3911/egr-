#!/usr/bin/env python3
"""
Локальный сборщик полного датасета ЕГР через period-эндпоинты.

Тянет 5 «по периоду» дампов за весь диапазон (как ты делал base через Postman),
мержит по УНП (ngrn) и пишет JSON в формате, который ест load_companies_from_json:
    [{"unp":.., "base_info":{...}, "addresses":[...], "ved":[...], "names":[...]}, ...]

Запуск локально (нужен только httpx):
    pip install httpx
    python egr_build_full_json.py --start 01.01.1994 --end 16.06.2026 --out egr_json_full

Затем залить egr_json_full/*.json на сервер в ~/egr/data/egr_json_full/ и:
    docker exec egr_celery_worker celery -A app.tasks.celery_app \
        call app.tasks.sync_tasks.load_companies_from_json --args='[true]'
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

import httpx

# По умолчанию http: egr.gov.by отдаёт leaf-сертификат без промежуточного,
# и локальные машины часто рвут TLS (UNEXPECTED_EOF). http стабильнее; при
# необходимости можно указать https через --base.
BASE = "http://egr.gov.by/api/v2/egr"
CAP_HINT = 2500          # если ответ == ~этому — возможно, эндпоинт обрезан
TIMEOUT = 180.0          # на одно окно; большое окно с обрывом → делится пополам


def _ngrn(rec: dict):
    return rec.get("ngrn") or rec.get("vunp") or rec.get("unp")


def _parse(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%d.%m.%Y").date()


def _fmt(d: dt.date) -> str:
    return d.strftime("%d.%m.%Y")


def _fetch_window(client: httpx.Client, endpoint: str, s_d: dt.date, e_d: dt.date) -> list:
    """
    Один запрос за окно [s_d, e_d]. Делит окно пополам если:
      • соединение оборвалось / таймаут (огромный ответ не докачался);
      • вернулось ≥CAP (возможный кап — делим ради полноты).
    Рекурсия до одного дня.
    """
    s, e = _fmt(s_d), _fmt(e_d)
    data = None
    last_err = None
    for _ in range(2):  # один повтор на транзиентный обрыв
        try:
            r = client.get(f"{BASE}/{endpoint}/{s}/{e}")
            if r.status_code != 200:
                print(f"    ! {endpoint} {s}-{e}: HTTP {r.status_code}", flush=True)
                return []
            j = r.json()
            data = j if isinstance(j, list) else []
            break
        except Exception as ex:
            last_err = ex

    def _split():
        mid = s_d + (e_d - s_d) // 2
        left = _fetch_window(client, endpoint, s_d, mid)
        right = _fetch_window(client, endpoint, mid + dt.timedelta(days=1), e_d)
        return left + right

    if data is None:
        if s_d >= e_d:
            print(f"    ! {endpoint} {s}: обрыв за один день — пропуск ({type(last_err).__name__})", flush=True)
            return []
        print(f"    ↯ {endpoint} {s}-{e}: обрыв большого ответа, делю окно пополам…", flush=True)
        return _split()

    # Капа 2500 у period-эндпоинтов нет (base отдаёт всё) — делим только при обрыве.
    print(f"    {s}–{e}: {len(data)}", flush=True)
    return data


def fetch(client: httpx.Client, endpoint: str, start: str, end: str, cache_dir: str) -> list:
    # Кэш на диск: повторный запуск НЕ перекачивает уже скачанные эндпоинты.
    # Чтобы перекачать заново — удали соответствующий файл в <out>/_cache/.
    cache_path = os.path.join(cache_dir, f"{endpoint}.json")
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            out = json.load(f)
        print(f"  ↺ {endpoint}: из кэша, {len(out)} записей", flush=True)
        return out

    print(f"  → {endpoint}: окно {start} → {end} (с авто-сплитом)", flush=True)
    out = _fetch_window(client, endpoint, _parse(start), _parse(end))

    tmp = cache_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp, cache_path)
    print(f"  ← {endpoint}: всего {len(out)} записей (сохранено в кэш)", flush=True)
    return out


def main():
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="01.01.1994")
    ap.add_argument("--end", default=dt.date.today().strftime("%d.%m.%Y"))
    ap.add_argument("--out", default="egr_json_full")
    ap.add_argument("--chunk", type=int, default=50000, help="компаний на один выходной файл")
    ap.add_argument("--prefix", default="egr_full", help="префикс имён выходных файлов (чтобы не конфликтовали с другим прогоном)")
    ap.add_argument("--base", default=BASE, help="базовый URL API (по умолчанию http, чтобы не упираться в TLS)")
    args = ap.parse_args()
    BASE = args.base.rstrip("/")

    os.makedirs(args.out, exist_ok=True)
    cache_dir = os.path.join(args.out, "_cache")
    os.makedirs(cache_dir, exist_ok=True)
    headers = {"User-Agent": "egr-full-export/1.0", "Accept": "application/json"}

    with httpx.Client(timeout=TIMEOUT, headers=headers, follow_redirects=True) as client:
        print("1/5 base_info"); base_recs = fetch(client, "getBaseInfoByPeriod", args.start, args.end, cache_dir)
        print("2/5 addresses"); addr_recs = fetch(client, "getAddressByPeriod", args.start, args.end, cache_dir)
        print("3/5 ved");       ved_recs  = fetch(client, "getVEDByPeriod", args.start, args.end, cache_dir)
        print("4/5 jur names"); jur_recs  = fetch(client, "getJurNamesByPeriod", args.start, args.end, cache_dir)
        print("5/5 ip fio");    ip_recs   = fetch(client, "getIPFIOByPeriod", args.start, args.end, cache_dir)

    # base: одна (последняя) запись на УНП
    base: dict = {}
    for rec in base_recs:
        u = _ngrn(rec)
        if u is None:
            continue
        prev = base.get(u)
        if prev is None or str(rec.get("dfrom", "")) >= str(prev.get("dfrom", "")):
            base[u] = rec

    def group(recs):
        g: dict = {}
        for rec in recs:
            u = _ngrn(rec)
            if u is not None:
                g.setdefault(u, []).append(rec)
        return g

    addr = group(addr_recs)
    ved = group(ved_recs)
    names = group(jur_recs)
    for u, lst in group(ip_recs).items():   # имена ИП — в тот же names
        names.setdefault(u, []).extend(lst)

    print(f"\nУникальных компаний (по base): {len(base)}", flush=True)

    part, written, buf = 0, 0, []

    def flush_buf():
        nonlocal part, buf
        if not buf:
            return
        path = os.path.join(args.out, f"{args.prefix}_{part:04d}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(buf, f, ensure_ascii=False)
        print(f"  ✓ {path}: {len(buf)} компаний", flush=True)
        part += 1
        buf = []

    for u, binfo in base.items():
        buf.append({
            "unp": u,
            "base_info": binfo,
            "addresses": addr.get(u, []),
            "ved": ved.get(u, []),
            "names": names.get(u, []),
        })
        written += 1
        if len(buf) >= args.chunk:
            flush_buf()
    flush_buf()

    print(f"\nГОТОВО: {written} компаний в {part} файлах ({args.out}/).", flush=True)
    print("Залей файлы на сервер в ~/egr/data/egr_json_full/ и запусти load_companies_from_json.", flush=True)


if __name__ == "__main__":
    main()
