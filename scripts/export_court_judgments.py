"""Export authenticated economic-court judgments to resumable JSONL."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Set


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.court_judgments import (  # noqa: E402
    COURTS,
    CourtAuthenticationError,
    CourtJudgment,
    CourtJudgmentClient,
    iter_court_filters,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    cookie = parser.add_mutually_exclusive_group(required=True)
    cookie.add_argument(
        "--cookie-file",
        type=Path,
        help="Path to a local Cookie header file; its contents are never logged",
    )
    cookie.add_argument(
        "--cookie-stdin",
        action="store_true",
        help="Read the Cookie header from stdin",
    )
    parser.add_argument("--date-from", default="01.01.2025")
    parser.add_argument("--date-to", default="31.01.2025")
    parser.add_argument(
        "--court",
        dest="courts",
        type=int,
        action="append",
        help="Court id; repeat for several courts (default: all economic courts)",
    )
    parser.add_argument("--type-proc", type=int, default=14)
    parser.add_argument("--category-dispute", type=int, default=0)
    parser.add_argument("--type-dispute", type=int, default=0)
    parser.add_argument(
        "--delay",
        type=float,
        default=300.0,
        help="Minimum seconds between every HTTP request (minimum/default: 300)",
    )
    parser.add_argument(
        "--delay-jitter",
        type=float,
        default=0.0,
        help="Additional random delay in seconds (default: 0)",
    )
    parser.add_argument("--max-pages", type=int)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("court-exports"),
    )
    parser.add_argument(
        "--download-documents",
        action="store_true",
        help="Also download the linked judgment documents",
    )
    return parser.parse_args()


def _read_cookie(args: argparse.Namespace) -> str:
    if args.cookie_stdin:
        value = sys.stdin.read().strip()
    else:
        value = args.cookie_file.read_text(encoding="utf-8-sig").strip()
    if not value:
        raise ValueError("Cookie input is empty")
    return value


def _validate_date(value: str) -> str:
    datetime.strptime(value, "%d.%m.%Y")
    return value


def _slug_date(value: str) -> str:
    return datetime.strptime(value, "%d.%m.%Y").date().isoformat()


def _load_existing_keys(path: Path) -> Set[str]:
    keys: Set[str] = set()
    if not path.exists():
        return keys
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {path}") from exc
            if row.get("key"):
                keys.add(str(row["key"]))
    return keys


def _load_state(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {"completed_pages": {}, "total_pages": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(path: Path, state: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _safe_document_name(record: CourtJudgment) -> str:
    case = re.sub(r"[^0-9A-Za-zА-Яа-яЁё._-]+", "_", record.case_number).strip("_")
    identity = record.document_id or record.process_id or record.key[-16:]
    return f"{record.court_id}_{record.judgment_date or 'unknown'}_{case}_{identity}.bin"


def _completed_pages(state: Dict[str, object], court_id: int) -> Set[int]:
    raw = state.setdefault("completed_pages", {}).setdefault(str(court_id), [])
    return {int(value) for value in raw}


def _write_page(
    handle: object,
    records: Iterable[CourtJudgment],
    seen: Set[str],
) -> int:
    written = 0
    for record in records:
        if record.key in seen:
            continue
        handle.write(json.dumps(record.as_dict(), ensure_ascii=False) + "\n")
        seen.add(record.key)
        written += 1
    handle.flush()
    return written


def main() -> int:
    args = parse_args()
    date_from = _validate_date(args.date_from)
    date_to = _validate_date(args.date_to)
    if datetime.strptime(date_from, "%d.%m.%Y") > datetime.strptime(date_to, "%d.%m.%Y"):
        raise ValueError("--date-from must not be after --date-to")
    if args.delay < 300:
        raise ValueError("--delay must be at least 300 seconds")
    if args.delay_jitter < 0:
        raise ValueError("--delay-jitter must not be negative")
    if args.max_pages is not None and args.max_pages < 1:
        raise ValueError("--max-pages must be at least 1")

    court_ids: List[int] = args.courts or list(COURTS)
    cookie_header = _read_cookie(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    all_courts = set(court_ids) == set(COURTS)
    court_slug = "all" if all_courts else "-".join(str(value) for value in court_ids)
    stem = (
        f"court_judgments_{_slug_date(date_from)}_{_slug_date(date_to)}"
        f"_proc{args.type_proc}_cat{args.category_dispute}"
        f"_type{args.type_dispute}_courts{court_slug}"
    )
    partial_path = args.output_dir / f"{stem}.jsonl.partial"
    final_path = args.output_dir / f"{stem}.jsonl"
    state_path = args.output_dir / f"{stem}.state.json"
    document_dir = args.output_dir / f"{stem}_documents"
    rate_limit_state_file = (
        args.cookie_file.parent / ".court-request-rate.txt"
        if args.cookie_file is not None
        else args.output_dir / ".court-request-rate.txt"
    )
    if final_path.exists():
        print(json.dumps({"status": "already_complete", "output": str(final_path)}))
        return 0

    state = _load_state(state_path)
    seen = _load_existing_keys(partial_path)
    fetched = 0
    written = 0
    downloaded = 0

    try:
        with CourtJudgmentClient(
            cookie_header,
            cookie_file=None if args.cookie_stdin else args.cookie_file,
            rate_limit_state_file=rate_limit_state_file,
            min_interval_seconds=args.delay,
            delay_jitter_seconds=args.delay_jitter,
        ) as client, partial_path.open(
            "a", encoding="utf-8", newline="\n"
        ) as output:
            for filters in iter_court_filters(
                court_ids,
                date_from=date_from,
                date_to=date_to,
                type_proc=args.type_proc,
                category_dispute=args.category_dispute,
                type_dispute=args.type_dispute,
            ):
                completed = _completed_pages(state, filters.court)
                totals = state.setdefault("total_pages", {})
                total_pages = int(totals.get(str(filters.court), 0))

                if not total_pages:
                    first_records, total_pages = client.fetch_page(filters, 1)
                    totals[str(filters.court)] = total_pages
                    fetched += len(first_records)
                    if 1 not in completed:
                        written += _write_page(output, first_records, seen)
                        if args.download_documents:
                            for record in first_records:
                                if record.download_url:
                                    target = document_dir / _safe_document_name(record)
                                    if not target.exists():
                                        client.download_document(record.download_url, target)
                                        downloaded += 1
                        completed.add(1)
                        state["completed_pages"][str(filters.court)] = sorted(completed)
                        _save_state(state_path, state)
                if args.max_pages is not None:
                    total_pages = min(total_pages, args.max_pages)
                for page in range(1, total_pages + 1):
                    if page in completed:
                        continue
                    records, reported_total = client.fetch_page(filters, page)
                    totals[str(filters.court)] = max(int(totals[str(filters.court)]), reported_total)
                    fetched += len(records)
                    written += _write_page(output, records, seen)
                    if args.download_documents:
                        for record in records:
                            if not record.download_url:
                                continue
                            target = document_dir / _safe_document_name(record)
                            if not target.exists():
                                client.download_document(record.download_url, target)
                                downloaded += 1
                    completed.add(page)
                    state["completed_pages"][str(filters.court)] = sorted(completed)
                    _save_state(state_path, state)
                    print(
                        json.dumps(
                            {
                                "court": filters.court,
                                "page": page,
                                "pages": total_pages,
                                "records": len(records),
                                "unique_total": len(seen),
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
    except CourtAuthenticationError as exc:
        print(str(exc), file=sys.stderr)
        print(f"Progress preserved in {partial_path} and {state_path}", file=sys.stderr)
        return 2

    complete = all(
        set(range(1, int(state["total_pages"][str(court_id)]) + 1))
        <= _completed_pages(state, court_id)
        for court_id in court_ids
    )
    if not complete:
        print(json.dumps({"status": "partial", "unique_total": len(seen),
                          "output": str(partial_path), "checkpoint": str(state_path)}))
        return 0
    os.replace(partial_path, final_path)
    state_path.unlink(missing_ok=True)
    print(
        json.dumps(
            {
                "status": "complete",
                "fetched": fetched,
                "written": written,
                "unique_total": len(seen),
                "documents_downloaded": downloaded,
                "output": str(final_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
