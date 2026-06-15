"""Resolve dirty company name lines to EGR UNP candidates.

Usage:
  python scripts/resolve_company_unps.py input.txt --output outputs/company_unp_matches.csv

The script is read-only: it does not modify EGR data. It searches local
PostgreSQL tables egr_companies and egr_company_names_history.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OPF_PATTERNS = [
    r"\bобщество\s+с\s+ограниченной\s+ответственностью\b",
    r"\bобщество\s+с\s+дополнительной\s+ответственностью\b",
    r"\bзакрытое\s+акционерное\s+общество\b",
    r"\bоткрытое\s+акционерное\s+общество\b",
    r"\bакционерное\s+общество\b",
    r"\bиндивидуальный\s+предприниматель\b",
    r"\bфизическое\s+лицо\b",
    r"\bчастное\s+предр?приятие\b",
    r"\bчастное\s+унитарное\s+предприятие\b",
    r"\bчастное\s+торговое\s+унитарное\s+предприятие\b",
    r"\bчастное\s+производственно[\s-]?торговое\s+предприятие\b",
    r"\bчастное\s+производственно[\s-]?торговое\s+унитарное\s+предприятие\b",
    r"\bунитарное\s+предприятие\b",
    r"\bреспубликанское\s+унитарное\s+предприятие\b",
    r"\bкоммунальное\s+унитарное\s+предприятие\b",
    r"\bсовместное\s+общество\s+с\s+ограниченной\s+ответственностью\b",
    r"\bсовместное\s+предприятие\b",
    r"\bфилиал\b",
    r"\bпредставительство\b",
    r"\bс\s*о\s*о\s*о\b",
    r"\bо\s*о\s*о\b",
    r"\bо\s*д\s*о\b",
    r"\bз\s*а\s*о\b",
    r"\bо\s*а\s*о\b",
    r"\bи\s*п\b",
    r"\bч\s*у\s*п\b",
    r"\bч\s*т\s*у\s*п\b",
    r"\bч\s*п\s*т\s*у\s*п\b",
    r"\bт\s*ч\s*у\s*п\b",
    r"\bт\s*п\s*ч\s*у\s*п\b",
    r"\bп\s*т\s*ч\s*у\s*п\b",
    r"\bу\s*п\b",
    r"\bр\s*у\s*п\b",
    r"\bс\s*п\b",
]

TRAILING_NOISE_PATTERNS = [
    r"\bс\s+ценой\b.*$",
    r"\b\d+[,.]\d+\s*бел\.?\s*руб\.?\b.*$",
    r"\b\d{6}\b",
    r"\bрб\b",
    r"\bреспублика\s+беларусь\b",
    r"\bг\.\s*[а-яёіў\- ]+\b",
    r"\bгород\s+[а-яёіў\- ]+\b",
    r"\bминская\s+область\b",
    r"\bгродненская\s+область\b",
    r"\bбрестская\s+область\b",
    r"\bвитебская\s+область\b",
    r"\bгомельская\s+область\b",
    r"\bмогилевская\s+область\b",
]


@dataclass
class Candidate:
    unp: int
    full_name_ru: str | None
    short_name_ru: str | None
    full_name_by: str | None
    matched_name: str | None
    matched_search_name: str | None
    matched_historical_name: bool
    db_score: float
    final_score: float


def strip_bom(value: str) -> str:
    return value.lstrip("\ufeff").strip()


def normalize_text(value: str | None, *, remove_opf: bool = True) -> str:
    if not value:
        return ""

    text_value = strip_bom(value)
    text_value = re.sub(r"([а-яёіў])([А-ЯЁІЎ])", r"\1 \2", text_value)
    text_value = text_value.lower().replace("ё", "е")
    text_value = text_value.replace("“", '"').replace("”", '"')
    text_value = text_value.replace("«", '"').replace("»", '"')
    text_value = text_value.replace("–", "-").replace("—", "-")

    for pattern in TRAILING_NOISE_PATTERNS:
        text_value = re.sub(pattern, " ", text_value, flags=re.IGNORECASE)

    if remove_opf:
        for pattern in OPF_PATTERNS:
            text_value = re.sub(pattern, " ", text_value, flags=re.IGNORECASE)

    text_value = re.sub(r"[^0-9a-zа-яеіў\s-]", " ", text_value)
    text_value = text_value.replace("-", " ")
    text_value = re.sub(r"\s+", " ", text_value).strip()
    return text_value


def quoted_parts(value: str) -> list[str]:
    normalized_quotes = (
        value.replace("“", '"')
        .replace("”", '"')
        .replace("«", '"')
        .replace("»", '"')
    )
    return [part.strip() for part in re.findall(r'"([^"]{2,})"', normalized_quotes) if part.strip()]


def make_query_variants(line: str) -> list[str]:
    variants: list[str] = []

    def add(value: str | None, *, remove_opf: bool = True) -> None:
        normalized = normalize_text(value, remove_opf=remove_opf)
        if normalized and normalized not in variants:
            variants.append(normalized)
        compact = normalized.replace(" ", "")
        if compact and compact != normalized and compact not in variants:
            variants.append(compact)

    add(line)
    add(line, remove_opf=False)
    for part in quoted_parts(line):
        add(part)
    return variants


def compact(value: str | None) -> str:
    return normalize_text(value).replace(" ", "")


def token_score(query: str, candidate: str) -> float:
    query_tokens = set(query.split())
    candidate_tokens = set(candidate.split())
    if not query_tokens or not candidate_tokens:
        return 0.0
    overlap = len(query_tokens & candidate_tokens)
    return overlap / max(len(query_tokens), 1)


def python_score(query_variants: list[str], candidate_name: str | None, candidate_search_name: str | None) -> float:
    names = [
        normalize_text(candidate_search_name),
        normalize_text(candidate_name),
        compact(candidate_search_name),
        compact(candidate_name),
    ]
    names = [name for name in names if name]
    best = 0.0
    for query in query_variants:
        for name in names:
            if not query or not name:
                continue
            if query == name:
                best = max(best, 1.0)
            if query in name or name in query:
                best = max(best, 0.92)
            best = max(best, SequenceMatcher(None, query, name).ratio())
            best = max(best, token_score(query, name) * 0.95)
    return best


def has_pg_trgm(db) -> bool:
    return bool(db.execute(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm')")).scalar())


def search_candidates(
    db,
    query_variants: list[str],
    *,
    limit: int,
    min_similarity: float,
    use_trgm: bool,
    trgm_variant_limit: int,
) -> list[dict[str, Any]]:
    if not query_variants:
        return []

    params: dict[str, Any] = {
        "limit": limit,
        "min_similarity": min_similarity,
    }
    conditions: list[str] = []
    score_terms: list[str] = ["0.0"]

    for idx, variant in enumerate(query_variants[:8]):
        key = f"q{idx}"
        prefix_key = f"prefix{idx}"
        params[key] = variant
        params[prefix_key] = f"{variant}%"

        conditions.append(
            f"""
            n.search_name = :{key}
            OR n.search_name LIKE :{prefix_key}
            """
        )
        score_terms.extend(
            [
                f"CASE WHEN n.search_name = :{key} THEN 1.0 ELSE 0.0 END",
                f"CASE WHEN n.search_name LIKE :{prefix_key} THEN 0.94 ELSE 0.0 END",
            ]
        )
        if use_trgm and idx < trgm_variant_limit and len(variant) <= 40:
            conditions.append(
                f"""
                n.search_name % :{key}
                """
            )
            score_terms.extend(
                [
                    f"similarity(coalesce(n.search_name, ''), :{key})",
                ]
            )

    sql = text(
        f"""
        WITH matches AS (
            SELECT
                c.unp,
                current_n.full_name_ru,
                current_n.short_name_ru,
                current_n.full_name_by,
                COALESCE(n.full_name_ru, n.short_name_ru, n.full_name_by) AS matched_name,
                n.search_name AS matched_search_name,
                n.valid_to IS NOT NULL AS matched_historical_name,
                GREATEST({", ".join(score_terms)}) AS db_score,
                c.liquidation_date
            FROM egr_company_names_history n
            JOIN egr_companies c ON c.id = n.company_id
            LEFT JOIN LATERAL (
                SELECT full_name_ru, short_name_ru, full_name_by
                FROM egr_company_names_history cn
                WHERE cn.company_id = c.id
                ORDER BY
                    (cn.valid_to IS NULL) DESC,
                    cn.valid_to DESC NULLS LAST,
                    cn.valid_from DESC NULLS LAST
                LIMIT 1
            ) current_n ON TRUE
            WHERE {" OR ".join(f"({condition})" for condition in conditions)}
        )
        SELECT DISTINCT ON (unp)
            unp,
            full_name_ru,
            short_name_ru,
            full_name_by,
            matched_name,
            matched_search_name,
            matched_historical_name,
            db_score
        FROM matches
        ORDER BY
            unp,
            (liquidation_date IS NULL) DESC,
            db_score DESC
        LIMIT :limit
        """
    )
    return list(db.execute(sql, params).mappings().all())


def pick_status(candidates: list[Candidate], auto_threshold: float, review_threshold: float) -> str:
    if not candidates:
        return "not_found"
    top = candidates[0]
    runner_up = candidates[1].final_score if len(candidates) > 1 else 0.0
    if top.final_score >= auto_threshold and top.final_score - runner_up >= 0.04:
        return "auto"
    if top.final_score >= review_threshold:
        return "review"
    return "not_found"


def resolve_line(
    db,
    line: str,
    *,
    limit: int,
    min_similarity: float,
    auto_threshold: float,
    review_threshold: float,
    use_trgm: bool,
    trgm_variant_limit: int,
) -> tuple[str, list[str], list[Candidate]]:
    variants = make_query_variants(line)
    rows = search_candidates(
        db,
        variants,
        limit=max(limit * 4, 20),
        min_similarity=min_similarity,
        use_trgm=use_trgm,
        trgm_variant_limit=trgm_variant_limit,
    )
    candidates: list[Candidate] = []
    for row in rows:
        display_name = row["matched_name"] or row["full_name_ru"] or row["short_name_ru"] or row["full_name_by"]
        py_score = python_score(variants, display_name, row["matched_search_name"])
        final_score = max(float(row["db_score"] or 0), py_score)
        candidates.append(
            Candidate(
                unp=int(row["unp"]),
                full_name_ru=row["full_name_ru"],
                short_name_ru=row["short_name_ru"],
                full_name_by=row["full_name_by"],
                matched_name=row["matched_name"],
                matched_search_name=row["matched_search_name"],
                matched_historical_name=bool(row["matched_historical_name"]),
                db_score=float(row["db_score"] or 0),
                final_score=final_score,
            )
        )
    candidates.sort(key=lambda item: item.final_score, reverse=True)
    candidates = candidates[:limit]
    return pick_status(candidates, auto_threshold, review_threshold), variants, candidates


def read_input_lines(path: Path) -> list[str]:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            with path.open("r", encoding=encoding) as handle:
                return [strip_bom(line) for line in handle if strip_bom(line)]
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("utf-8", b"", 0, 1, f"Unable to decode {path}")


def write_report(path: Path, rows: list[dict[str, Any]]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        raise PermissionError(
            f"Cannot create output directory {path.parent}. "
            "Use a writable path, for example /tmp/company_unp_matches.csv "
            "or /app/data/company_unp_matches.csv."
        ) from exc
    fieldnames = [
        "row_no",
        "status",
        "input",
        "normalized",
        "candidate_rank",
        "unp",
        "score",
        "db_score",
        "name",
        "matched_name",
        "matched_historical_name",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def create_db_session():
    from app.core.database import SessionLocal

    return SessionLocal()


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve dirty company name lines to UNP candidates.")
    parser.add_argument("input", type=Path, help="Text file: one company string per line")
    parser.add_argument("--output", type=Path, default=Path("outputs/company_unp_matches.csv"))
    parser.add_argument("--limit", type=int, default=3, help="Candidates per input line")
    parser.add_argument("--min-similarity", type=float, default=0.28, help="pg_trgm candidate threshold")
    parser.add_argument("--auto-threshold", type=float, default=0.86)
    parser.add_argument("--review-threshold", type=float, default=0.68)
    parser.add_argument("--no-trgm", action="store_true", help="Disable pg_trgm usage even if installed")
    parser.add_argument("--max-rows", type=int, default=None, help="Process only first N input rows")
    parser.add_argument("--progress-every", type=int, default=10, help="Print progress every N rows")
    parser.add_argument("--statement-timeout", type=int, default=20, help="Per-query timeout in seconds")
    parser.add_argument("--trgm-variant-limit", type=int, default=2, help="Use pg_trgm only for first N variants")
    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be greater than zero")
    if args.max_rows is not None and args.max_rows < 1:
        parser.error("--max-rows must be greater than zero")
    if not args.input.exists():
        raise FileNotFoundError(args.input)

    input_lines = read_input_lines(args.input)
    if args.max_rows is not None:
        input_lines = input_lines[: args.max_rows]

    report_rows: list[dict[str, Any]] = []
    stats = {"total": 0, "auto": 0, "review": 0, "not_found": 0}

    db = create_db_session()
    try:
        use_trgm = False if args.no_trgm else has_pg_trgm(db)
        if use_trgm:
            db.execute(text(f"SELECT set_limit({float(args.min_similarity)})"))
        if args.statement_timeout > 0:
            db.execute(text(f"SET statement_timeout = {int(args.statement_timeout * 1000)}"))
        print(f"Loaded {len(input_lines)} rows. pg_trgm={'on' if use_trgm else 'off'}", flush=True)

        for row_no, line in enumerate(input_lines, start=1):
            try:
                status, variants, candidates = resolve_line(
                    db,
                    line,
                    limit=args.limit,
                    min_similarity=args.min_similarity,
                    auto_threshold=args.auto_threshold,
                    review_threshold=args.review_threshold,
                    use_trgm=use_trgm,
                    trgm_variant_limit=args.trgm_variant_limit,
                )
            except Exception as exc:
                db.rollback()
                status = "not_found"
                variants = make_query_variants(line)
                candidates = []
                error_text = str(exc).splitlines()[0]
                print(f"row {row_no} skipped after query error: {type(exc).__name__}: {error_text}", flush=True)
            stats["total"] += 1
            stats[status] += 1

            if not candidates:
                report_rows.append(
                    {
                        "row_no": row_no,
                        "status": status,
                        "input": line,
                        "normalized": " | ".join(variants),
                        "candidate_rank": None,
                        "unp": None,
                        "score": None,
                        "db_score": None,
                        "name": None,
                        "matched_name": None,
                        "matched_historical_name": None,
                    }
                )
            else:
                for rank, candidate in enumerate(candidates, start=1):
                    report_rows.append(
                        {
                            "row_no": row_no,
                            "status": status if rank == 1 else "candidate",
                            "input": line,
                            "normalized": " | ".join(variants),
                            "candidate_rank": rank,
                            "unp": candidate.unp,
                            "score": round(candidate.final_score, 4),
                            "db_score": round(candidate.db_score, 4),
                            "name": candidate.full_name_ru or candidate.short_name_ru or candidate.full_name_by,
                            "matched_name": candidate.matched_name,
                            "matched_historical_name": candidate.matched_historical_name,
                        }
                    )

            if args.progress_every > 0 and row_no % args.progress_every == 0:
                print(stats, flush=True)
    finally:
        db.close()

    write_report(args.output, report_rows)
    found = stats["auto"] + stats["review"]
    found_pct = round((found / stats["total"] * 100), 2) if stats["total"] else 0
    print(
        {
            **stats,
            "found_auto_or_review": found,
            "found_pct": found_pct,
            "output": str(args.output),
        },
        flush=True,
    )


if __name__ == "__main__":
    main()
