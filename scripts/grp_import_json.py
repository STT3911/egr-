#!/usr/bin/env python3
"""
Импорт локально-собранного ГРП JSONL в БД (raw + parsed). Без обращений к API.

Запуск внутри контейнера (код примонтирован в /app):
  docker exec -d egr_celery_worker python scripts/grp_import_json.py /app/data/grp_import/grp_data.jsonl

Каждая строка JSONL: {"unp":.., "raw_json":{...}|{}, "http_status":.., "error":..}
Идемпотентно: повторный запуск безопасен (upsert по UNP).
"""
import json
import sys

from app.core.database import SessionLocal
from app.crud.grp import GrpCRUD


def main(path: str):
    db = SessionLocal()
    crud = GrpCRUD(db)
    total = parsed = errors = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                unp = int(rec["unp"])
            except Exception:
                continue
            raw = rec.get("raw_json")
            crud.save_raw_data(
                unp=unp,
                raw_json=raw,
                http_status=rec.get("http_status"),
                error=rec.get("error"),
            )
            if isinstance(raw, dict) and raw and not rec.get("error"):
                try:
                    crud.parse_from_raw(unp)
                    parsed += 1
                except Exception:
                    errors += 1
            total += 1
            if total % 1000 == 0:
                db.commit()
                print(f"imported {total} (parsed {parsed}, parse_err {errors})", flush=True)
    db.commit()
    db.close()
    print(f"DONE: imported {total}, parsed {parsed}, parse_err {errors}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: grp_import_json.py <path.jsonl>")
        sys.exit(1)
    main(sys.argv[1])
