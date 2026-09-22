"""Bounded-memory EGR JSON export. Never publish an incomplete snapshot."""
import asyncio
import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path


async def export_snapshot(client, start, end, directory, *, min_free_mb=2048, parallel=4, row_limit=2500):
    first = datetime.strptime(start, "%d.%m.%Y").date()
    last = datetime.strptime(end, "%d.%m.%Y").date()
    if first > last or parallel < 1:
        raise ValueError("Invalid export interval/batch size")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    def check_space():
        if shutil.disk_usage(directory).free < min_free_mb * 1024 * 1024:
            raise RuntimeError("Insufficient free disk for EGR export; existing snapshots preserved")
    check_space()
    final = directory / f"{start.replace('.', '-')}_to_{end.replace('.', '-')}.json"
    # Verify permissions BEFORE issuing upstream requests. Unique temporary
    # paths preserve previous partial exports for diagnosis.
    fd, temporary = tempfile.mkstemp(prefix=final.name + ".", suffix=".partial", dir=directory)
    count = 0
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("[")
            day = first
            while day <= last:
                check_space()
                rows = await client.get_period_rows("getBaseInfoByPeriod", day.strftime("%d.%m.%Y"))
                if row_limit and len(rows) >= row_limit:
                    raise ValueError("Potentially truncated daily EGR snapshot; refusing publication")
                unps = sorted({int(row["ngrn"]) for row in rows})
                # No multi-year list of base rows or full histories in memory.
                for offset in range(0, len(unps), parallel):
                    check_space()
                    batch = unps[offset:offset + parallel]
                    results = await asyncio.gather(*[
                        client.get_full_company_history_strict(unp) for unp in batch
                    ], return_exceptions=True)
                    for unp, payload in zip(batch, results):
                        if isinstance(payload, BaseException):
                            raise payload
                        if count:
                            stream.write(",")
                        json.dump({"unp": unp, **payload}, stream, ensure_ascii=False)
                        count += 1
                    stream.flush()
                    await asyncio.sleep(0.5)
                day += timedelta(days=1)
                await asyncio.sleep(0.5)
            stream.write("]")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, final)
        return count
    except BaseException:
        # Never rename incomplete data to *.json (the importer scans *.json).
        raise
