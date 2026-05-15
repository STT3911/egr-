"""Check trade registry UNPs missing in local DB against the EGR API.

Usage:
  python scripts/check_trade_registry_missing_in_egr.py \
    data/imports/reports/trade_registry_missing_unps.csv \
    --output data/imports/reports/trade_registry_missing_egr_check.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def extract_unp(row: dict[str, Any]) -> int | None:
    value = row.get("__parsed_unp") or row.get("УНП")
    text = clean_text(value)
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    return int(digits)


def read_unique_unps(csv_path: Path, limit: int | None = None) -> list[int]:
    seen = set()
    unps = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            unp = extract_unp(row)
            if unp is None or unp in seen:
                continue
            seen.add(unp)
            unps.append(unp)
            if limit is not None and len(unps) >= limit:
                break
    return unps


def base_info_name(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    return clean_text(payload.get("vnaim")) or clean_text(payload.get("vfio")) or clean_text(payload.get("VNAIM")) or clean_text(payload.get("VFIO"))


def mobile_info_name(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    return (
        clean_text(payload.get("fullNameRus"))
        or clean_text(payload.get("shortNameRus"))
        or clean_text(payload.get("fullNameBel"))
    )


def compact_json(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


async def check_unp(
    unp: int,
    egr_client: EGRClient,
    mobile_client: MobileEGRClient | None,
    semaphore: asyncio.Semaphore,
    delay: float,
) -> dict[str, Any]:
    async with semaphore:
        if delay > 0:
            await asyncio.sleep(delay)
        row: dict[str, Any] = {
            "unp": unp,
            "status": "not_found",
            "legacy_found": False,
            "mobile_found": False,
            "name": None,
            "legacy_raw": None,
            "mobile_raw": None,
            "error": None,
        }
        try:
            legacy = await egr_client.get_base_info(unp)
            if legacy:
                row["status"] = "found"
                row["legacy_found"] = True
                row["name"] = base_info_name(legacy)
                row["legacy_raw"] = compact_json(legacy)
                return row

            if mobile_client is not None:
                mobile = await mobile_client.get_common_info(str(unp))
                if mobile:
                    row["status"] = "found"
                    row["mobile_found"] = True
                    row["name"] = mobile_info_name(mobile)
                    row["mobile_raw"] = compact_json(mobile)
            return row
        except Exception as exc:
            row["status"] = "error"
            row["error"] = repr(exc)
    return row


async def save_found_company(unp: int) -> tuple[bool, str | None]:
    from app.services.aggregator import AggregatorService

    aggregator = AggregatorService()
    try:
        fetched = await aggregator.fetch_and_save_raw(unp)
        if not fetched:
            return False, "EGR returned no raw data"
        aggregator.process_raw_data(unp)
        return True, None
    except Exception as exc:
        return False, repr(exc)
    finally:
        aggregator.close()


async def run_check(
    unps: list[int],
    output_path: Path,
    concurrency: int,
    delay: float,
    save_found: bool,
) -> dict[str, int]:
    from app.core.config import settings
    from app.services.egr_client import EGRClient, MobileEGRClient

    egr_client = EGRClient(settings.EGR_API_URL)
    mobile_client = MobileEGRClient(settings.EGR_MOBILE_API_URL) if settings.EGR_MOBILE_API_URL else None
    semaphore = asyncio.Semaphore(concurrency)
    fieldnames = [
        "unp",
        "status",
        "legacy_found",
        "mobile_found",
        "saved_to_db",
        "name",
        "error",
        "save_error",
        "legacy_raw",
        "mobile_raw",
    ]
    stats = {"checked": 0, "found": 0, "not_found": 0, "error": 0, "saved_to_db": 0, "save_error": 0}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()

            for start in range(0, len(unps), concurrency):
                chunk = unps[start:start + concurrency]
                results = await asyncio.gather(
                    *(check_unp(unp, egr_client, mobile_client, semaphore, delay) for unp in chunk)
                )
                for row in results:
                    row["saved_to_db"] = False
                    row["save_error"] = None
                    if save_found and row["status"] == "found":
                        saved, save_error = await save_found_company(int(row["unp"]))
                        row["saved_to_db"] = saved
                        row["save_error"] = save_error
                        if saved:
                            stats["saved_to_db"] += 1
                        else:
                            stats["save_error"] += 1

                    writer.writerow(row)
                    stats["checked"] += 1
                    stats[row["status"]] += 1

                if stats["checked"] % 100 == 0:
                    print(json.dumps(stats, ensure_ascii=False), flush=True)
    finally:
        await egr_client.close()
        if mobile_client is not None:
            await mobile_client.close()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Check missing trade registry UNPs against EGR.")
    parser.add_argument("missing_csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--delay", type=float, default=0.2, help="Delay before each request, seconds")
    parser.add_argument("--save-found", action="store_true", help="Fetch, parse, and save found companies into local DB")
    args = parser.parse_args()

    if not args.missing_csv.exists():
        raise FileNotFoundError(args.missing_csv)
    if args.concurrency < 1:
        parser.error("--concurrency must be greater than zero")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be greater than zero")

    unps = read_unique_unps(args.missing_csv, args.limit)
    print(f"Loaded {len(unps)} unique UNPs from {args.missing_csv}", flush=True)
    stats = asyncio.run(run_check(unps, args.output, args.concurrency, args.delay, args.save_found))
    print(json.dumps({**stats, "output": str(args.output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
