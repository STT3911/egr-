#!/usr/bin/env python3
"""Check UNPs in EGR and GRP, persist both sources, and report results."""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.core.database import SessionLocal
from app.crud.grp import GrpCRUD
from app.services.aggregator import AggregatorService
from app.services.company_registry import sync_company_from_grp
from app.services.grp_client import GRPClient


REPORT_FIELDS = (
    "unp",
    "status",
    "egr_status",
    "grp_status",
    "egr_parsed",
    "grp_parsed",
    "egr_name",
    "grp_name",
    "egr_source",
    "grp_http_status",
    "error",
)
FINAL_STATUSES = {"found", "not_found", "invalid"}


@dataclass(frozen=True)
class SourceResult:
    unp: str
    source: str
    status: str
    payload: dict | None = None
    http_status: int | None = None
    source_variant: str = ""
    error: str = ""


def read_unps(path: Path | None, positional: list[str]) -> list[str]:
    values = list(positional)
    if path is not None:
        values.extend(path.read_text(encoding="utf-8-sig").splitlines())

    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        unp = value.strip()
        if not unp or unp in seen:
            continue
        seen.add(unp)
        unique.append(unp)
    return unique


def load_report(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as report_file:
        return {
            row["unp"]: row
            for row in csv.DictReader(report_file)
            if row.get("unp")
        }


def _write_list(path: Path, values: list[str]) -> None:
    path.write_text("".join(f"{value}\n" for value in values), encoding="utf-8")


def write_outputs(
    report_path: Path,
    ordered_unps: list[str],
    results: dict[str, dict[str, str]],
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = report_path.with_suffix(report_path.suffix + ".tmp")
    with tmp_path.open("w", newline="", encoding="utf-8-sig") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        for unp in ordered_unps:
            row = results.get(unp)
            if row:
                writer.writerow({field: row.get(field, "") for field in REPORT_FIELDS})
    os.replace(tmp_path, report_path)

    for status in ("found", "not_found", "error", "invalid"):
        values = [unp for unp in ordered_unps if results.get(unp, {}).get("status") == status]
        _write_list(report_path.with_name(f"{report_path.stem}.{status}.txt"), values)

    egr_found = [unp for unp in ordered_unps if results.get(unp, {}).get("egr_status") == "found"]
    grp_found = [unp for unp in ordered_unps if results.get(unp, {}).get("grp_status") == "found"]
    _write_list(report_path.with_name(f"{report_path.stem}.egr_found.txt"), egr_found)
    _write_list(report_path.with_name(f"{report_path.stem}.grp_found.txt"), grp_found)


def print_summary(report_path: Path, results: dict[str, dict[str, str]]) -> None:
    overall = Counter(row.get("status", "pending") for row in results.values())
    egr = Counter(row.get("egr_status", "pending") for row in results.values())
    grp = Counter(row.get("grp_status", "pending") for row in results.values())
    found_both = sum(
        row.get("egr_status") == "found" and row.get("grp_status") == "found"
        for row in results.values()
    )
    print("=" * 72)
    print(f"report: {report_path}")
    print(f"processed: {sum(overall.values())}")
    print(f"found_any_source: {overall['found']}")
    print(f"not_found_in_both: {overall['not_found']}")
    print(f"errors: {overall['error']}")
    print(f"invalid: {overall['invalid']}")
    print(f"egr_found: {egr['found']}")
    print(f"egr_not_found: {egr['not_found']}")
    print(f"grp_found: {grp['found']}")
    print(f"grp_not_found: {grp['not_found']}")
    print(f"found_in_both: {found_both}")
    print(f"found_list: {report_path.with_name(report_path.stem + '.found.txt')}")
    print(f"not_found_list: {report_path.with_name(report_path.stem + '.not_found.txt')}")
    print(f"egr_found_list: {report_path.with_name(report_path.stem + '.egr_found.txt')}")
    print(f"grp_found_list: {report_path.with_name(report_path.stem + '.grp_found.txt')}")
    print("=" * 72)


def _egr_name(payload: dict | None) -> str:
    if not payload:
        return ""
    base = payload.get("base_info") or payload.get("common_info") or {}
    for key in ("vnaim", "VNAIM", "vfio", "VFIO", "fullNameRus", "shortNameRus"):
        value = base.get(key)
        if value:
            return str(value).strip()
    return ""


def _grp_name(payload: dict | None) -> str:
    if not payload:
        return ""
    return str(
        payload.get("VNAIMP")
        or payload.get("vnaimp")
        or payload.get("VNAIMK")
        or payload.get("vnaimk")
        or ""
    ).strip()


async def fetch_egr(aggregator: AggregatorService, unp: str) -> SourceResult:
    if not unp.isdigit():
        return SourceResult(unp=unp, source="egr", status="invalid", error="UNP must contain digits only")
    try:
        payload = await aggregator.egr_client.get_full_company_history(int(unp))
        if payload:
            return SourceResult(
                unp=unp,
                source="egr",
                status="found",
                payload=payload,
                http_status=200,
                source_variant="legacy",
            )
        if aggregator.mobile_client is not None:
            common_info = await aggregator.mobile_client.get_common_info(unp)
            if common_info:
                return SourceResult(
                    unp=unp,
                    source="egr",
                    status="found",
                    payload={"common_info": common_info, "place_location": None},
                    http_status=200,
                    source_variant="mobile",
                )
        return SourceResult(unp=unp, source="egr", status="not_found", http_status=404)
    except Exception as exc:
        return SourceResult(unp=unp, source="egr", status="error", error=repr(exc))


async def fetch_grp(
    client: GRPClient,
    unp: str,
    max_retries: int,
    retry_delay: float,
    cooldown: float,
) -> SourceResult:
    if not unp.isdigit():
        return SourceResult(unp=unp, source="grp", status="invalid", error="UNP must contain digits only")

    attempt = 0
    while True:
        try:
            payload = await client.get_taxpayer(int(unp))
            if not payload:
                return SourceResult(unp=unp, source="grp", status="not_found", http_status=404)
            returned_unp = payload.get("VUNP") or payload.get("vunp")
            if returned_unp and str(returned_unp) != unp:
                return SourceResult(
                    unp=unp,
                    source="grp",
                    status="error",
                    http_status=200,
                    error=f"GRP returned UNP {returned_unp}",
                )
            return SourceResult(unp=unp, source="grp", status="found", payload=payload, http_status=200)
        except httpx.HTTPStatusError as exc:
            http_status = exc.response.status_code if exc.response is not None else None
            if http_status is not None and 400 <= http_status < 500 and http_status != 429:
                return SourceResult(unp=unp, source="grp", status="not_found", http_status=http_status)
            attempt += 1
            if attempt > max_retries:
                return SourceResult(
                    unp=unp,
                    source="grp",
                    status="error",
                    http_status=http_status,
                    error=str(exc),
                )
            await asyncio.sleep(cooldown if http_status == 429 else retry_delay * attempt)
        except (httpx.HTTPError, ValueError) as exc:
            attempt += 1
            if attempt > max_retries:
                return SourceResult(unp=unp, source="grp", status="error", error=str(exc))
            await asyncio.sleep(retry_delay * attempt)


def persist_egr(aggregator: AggregatorService, result: SourceResult) -> tuple[bool, str]:
    if result.status != "found" or not result.payload:
        return False, ""
    try:
        raw_entry = aggregator.save_raw_payload(int(result.unp), result.payload)
        aggregator.process_raw_data(int(result.unp), raw_entry=raw_entry)
        return True, ""
    except Exception as exc:
        return False, f"EGR parse: {exc}"


def persist_grp(result: SourceResult) -> tuple[bool, str]:
    if result.status in {"invalid", "error"}:
        return False, ""
    db = SessionLocal()
    try:
        crud = GrpCRUD(db)
        unp = int(result.unp)
        if result.status == "found" and result.payload:
            parsed = crud.upsert_from_api(unp=unp, payload=result.payload, http_status=200)
            if parsed is None or not sync_company_from_grp(db, unp):
                raise RuntimeError("GRP payload could not be materialized in egr_companies")
        elif result.status == "not_found":
            crud.save_raw_data(unp=unp, raw_json={}, http_status=result.http_status)
        db.commit()
        return result.status == "found", ""
    except Exception as exc:
        db.rollback()
        return False, f"GRP parse: {exc}"
    finally:
        db.close()


def build_row(
    aggregator: AggregatorService,
    egr_result: SourceResult,
    grp_result: SourceResult,
) -> dict[str, str]:
    egr_parsed, egr_parse_error = persist_egr(aggregator, egr_result)
    grp_parsed, grp_parse_error = persist_grp(grp_result)
    errors = [
        value
        for value in (
            egr_result.error if egr_result.status == "error" else "",
            grp_result.error if grp_result.status == "error" else "",
            egr_parse_error,
            grp_parse_error,
        )
        if value
    ]

    if egr_result.status == "invalid" and grp_result.status == "invalid":
        status = "invalid"
    elif errors:
        status = "error"
    elif "found" in {egr_result.status, grp_result.status}:
        status = "found"
    else:
        status = "not_found"

    return {
        "unp": egr_result.unp,
        "status": status,
        "egr_status": egr_result.status,
        "grp_status": grp_result.status,
        "egr_parsed": "yes" if egr_parsed else "no",
        "grp_parsed": "yes" if grp_parsed else "no",
        "egr_name": _egr_name(egr_result.payload),
        "grp_name": _grp_name(grp_result.payload),
        "egr_source": egr_result.source_variant,
        "grp_http_status": str(grp_result.http_status or ""),
        "error": " | ".join(errors),
    }


async def run(args: argparse.Namespace) -> int:
    input_path = Path(args.file).resolve() if args.file else None
    report_path = Path(args.report).resolve()
    unps = read_unps(input_path, args.unp)
    if not unps:
        print("No UNPs found in input", file=sys.stderr)
        return 2

    input_unps = set(unps)
    loaded_results = {} if args.fresh else load_report(report_path)
    results = {unp: row for unp, row in loaded_results.items() if unp in input_unps}
    all_pending = [unp for unp in unps if results.get(unp, {}).get("status") not in FINAL_STATUSES]
    pending = all_pending[: args.limit] if args.limit is not None else all_pending

    print(f"input: {len(unps)} unique UNPs")
    print(f"already processed: {len(unps) - len(all_pending)}")
    print(f"to request from EGR and GRP: {len(pending)}")
    if len(all_pending) > len(pending):
        print(f"left after this run: {len(all_pending) - len(pending)}")

    aggregator = AggregatorService()
    grp_client = GRPClient(timeout=args.timeout)
    processed_now = 0
    try:
        for offset in range(0, len(pending), args.concurrency):
            batch = pending[offset : offset + args.concurrency]
            source_tasks = []
            for unp in batch:
                source_tasks.append(fetch_egr(aggregator, unp))
                source_tasks.append(
                    fetch_grp(
                        grp_client,
                        unp,
                        max_retries=args.max_retries,
                        retry_delay=args.retry_delay,
                        cooldown=args.cooldown,
                    )
                )
            source_results = await asyncio.gather(*source_tasks)

            for index, unp in enumerate(batch):
                egr_result = source_results[index * 2]
                grp_result = source_results[index * 2 + 1]
                row = build_row(aggregator, egr_result, grp_result)
                results[unp] = row
                processed_now += 1
                print(
                    f"[{processed_now}/{len(pending)}] {row['status'].upper()} {unp} "
                    f"| EGR={row['egr_status'].upper()} GRP={row['grp_status'].upper()}",
                    flush=True,
                )

            write_outputs(report_path, unps, results)
            if offset + args.concurrency < len(pending):
                await asyncio.sleep(args.delay)
    finally:
        await grp_client.close()
        await aggregator.egr_client.close()
        if aggregator.mobile_client is not None:
            await aggregator.mobile_client.close()
        aggregator.close()
        write_outputs(report_path, unps, results)

    print_summary(report_path, results)
    return 1 if any(row.get("status") == "error" for row in results.values()) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check UNPs in EGR and GRP, import both sources, and write result lists",
    )
    parser.add_argument("unp", nargs="*", help="UNPs passed directly")
    parser.add_argument("--file", help="TXT file with one UNP per line")
    parser.add_argument("--report", default="data/client_unp_report.csv", help="CSV report path")
    parser.add_argument("--fresh", action="store_true", help="request every UNP again")
    parser.add_argument("--status", action="store_true", help="show current report statistics and exit")
    parser.add_argument("--limit", type=int, help="process at most N pending UNPs")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--delay", type=float, default=2.0, help="delay between request batches")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--max-retries", type=int, default=settings.GRP_FETCH_MAX_RETRIES)
    parser.add_argument("--retry-delay", type=float, default=settings.GRP_FETCH_RETRY_BASE_DELAY_SECONDS)
    parser.add_argument("--cooldown", type=float, default=settings.GRP_FETCH_RETRY_COOLDOWN_MINUTES * 60.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report_path = Path(args.report).resolve()
    if args.status:
        print_summary(report_path, load_report(report_path))
        raise SystemExit(0)
    if not args.file and not args.unp:
        raise SystemExit("Pass --file or at least one UNP")
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
