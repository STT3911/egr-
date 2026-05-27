"""Import export.by company cards and link them to EGR companies by UNP."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database.models import ExportByCompanyRecord
from app.core.logger import get_logger
from app.utils.search_normalizer import normalize_company_name


logger = get_logger("export_by_import")

MATCHED = "matched"
AMBIGUOUS = "ambiguous"
NOT_FOUND = "not_found"
INVALID_NAME = "invalid_name"


@dataclass
class CompanyNameCandidate:
    company_id: Any
    unp: int
    matched_name: str | None
    score: float
    method: str

    def as_json(self) -> dict[str, Any]:
        return {
            "company_id": str(self.company_id),
            "unp": self.unp,
            "matched_name": self.matched_name,
            "score": round(self.score, 4),
            "method": self.method,
        }


@dataclass
class NameMatch:
    status: str
    method: str | None = None
    candidate: CompanyNameCandidate | None = None
    candidates: list[CompanyNameCandidate] | None = None

    @property
    def candidate_json(self) -> list[dict[str, Any]]:
        return [candidate.as_json() for candidate in self.candidates or []]


def _has_pg_trgm(db: Any) -> bool:
    return bool(
        db.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_proc
                    WHERE proname = 'similarity'
                )
                """
            )
        ).scalar()
    )


def _dedupe_candidates(rows: list[Any], method: str) -> list[CompanyNameCandidate]:
    seen: set[int] = set()
    candidates: list[CompanyNameCandidate] = []
    for row in rows:
        unp = int(row["unp"])
        if unp in seen:
            continue
        seen.add(unp)
        candidates.append(
            CompanyNameCandidate(
                company_id=row["company_id"],
                unp=unp,
                matched_name=row["matched_name"],
                score=float(row["score"]),
                method=method,
            )
        )
    return candidates


def find_company_match_by_name(
    db: Any,
    name: str,
    fuzzy_threshold: float = 0.86,
    fuzzy_margin: float = 0.08,
    candidate_limit: int = 10,
    use_fuzzy: bool = True,
    pg_trgm_available: bool | None = None,
) -> tuple[str | None, NameMatch]:
    """Resolve a source company name to exactly one EGR company when confidence is high."""

    normalized = normalize_company_name(name)
    if not normalized:
        return None, NameMatch(status=INVALID_NAME)

    exact_rows = (
        db.execute(
            text(
                """
                SELECT DISTINCT ON (c.unp)
                    c.id AS company_id,
                    c.unp,
                    COALESCE(n.full_name_ru, n.short_name_ru, n.full_name_by) AS matched_name,
                    1.0 AS score
                FROM egr_companies c
                JOIN egr_company_names_history n ON n.company_id = c.id
                WHERE n.search_name = :normalized
                ORDER BY
                    c.unp,
                    (n.valid_to IS NULL) DESC,
                    n.valid_to DESC NULLS LAST,
                    n.valid_from DESC NULLS LAST
                LIMIT :candidate_limit
                """
            ),
            {"normalized": normalized, "candidate_limit": candidate_limit},
        )
        .mappings()
        .all()
    )
    exact_candidates = _dedupe_candidates(exact_rows, "exact_search_name")
    if len(exact_candidates) == 1:
        return normalized, NameMatch(
            status=MATCHED,
            method="exact_search_name",
            candidate=exact_candidates[0],
            candidates=exact_candidates,
        )
    if len(exact_candidates) > 1:
        return normalized, NameMatch(
            status=AMBIGUOUS,
            method="exact_search_name",
            candidates=exact_candidates,
        )

    if pg_trgm_available is None:
        pg_trgm_available = _has_pg_trgm(db) if use_fuzzy else False
    if not use_fuzzy or not pg_trgm_available:
        return normalized, NameMatch(status=NOT_FOUND, candidates=[])

    fuzzy_rows = (
        db.execute(
            text(
                """
                SELECT
                    c.id AS company_id,
                    c.unp,
                    COALESCE(n.full_name_ru, n.short_name_ru, n.full_name_by) AS matched_name,
                    similarity(n.search_name, :normalized) AS score
                FROM egr_companies c
                JOIN egr_company_names_history n ON n.company_id = c.id
                WHERE n.search_name IS NOT NULL
                  AND similarity(n.search_name, :normalized) >= :threshold
                ORDER BY
                    score DESC,
                    (n.valid_to IS NULL) DESC,
                    n.valid_to DESC NULLS LAST,
                    n.valid_from DESC NULLS LAST
                LIMIT :candidate_limit
                """
            ),
            {
                "normalized": normalized,
                "threshold": fuzzy_threshold,
                "candidate_limit": candidate_limit,
            },
        )
        .mappings()
        .all()
    )
    fuzzy_candidates = _dedupe_candidates(fuzzy_rows, "trigram_similarity")
    if not fuzzy_candidates:
        return normalized, NameMatch(status=NOT_FOUND, candidates=[])

    top = fuzzy_candidates[0]
    second_score = fuzzy_candidates[1].score if len(fuzzy_candidates) > 1 else 0.0
    if top.score >= fuzzy_threshold and top.score - second_score >= fuzzy_margin:
        return normalized, NameMatch(
            status=MATCHED,
            method="trigram_similarity",
            candidate=top,
            candidates=fuzzy_candidates,
        )

    return normalized, NameMatch(
        status=AMBIGUOUS,
        method="trigram_similarity",
        candidates=fuzzy_candidates,
    )


def upsert_export_by_record(db: Any, source_row: dict[str, Any], normalized_name: str | None, match: NameMatch) -> None:
    candidate = match.candidate
    now = datetime.utcnow()
    values = {
        "export_by_id": int(source_row["id"]),
        "company_id": candidate.company_id if candidate else None,
        "unp": candidate.unp if candidate else None,
        "name": source_row.get("name") or "",
        "normalized_name": normalized_name,
        "logo": source_row.get("logo") or None,
        "description": source_row.get("description") or None,
        "country": source_row.get("country") or None,
        "is_favorite": bool(source_row.get("is_favorite")),
        "match_status": match.status,
        "match_method": match.method,
        "match_score": candidate.score if candidate else None,
        "matched_name": candidate.matched_name if candidate else None,
        "candidate_unps": match.candidate_json,
        "raw_json": source_row,
        "last_seen_at": now,
        "updated_at": now,
    }
    stmt = pg_insert(ExportByCompanyRecord).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[ExportByCompanyRecord.export_by_id],
        set_={
            "company_id": stmt.excluded.company_id,
            "unp": stmt.excluded.unp,
            "name": stmt.excluded.name,
            "normalized_name": stmt.excluded.normalized_name,
            "logo": stmt.excluded.logo,
            "description": stmt.excluded.description,
            "country": stmt.excluded.country,
            "is_favorite": stmt.excluded.is_favorite,
            "match_status": stmt.excluded.match_status,
            "match_method": stmt.excluded.match_method,
            "match_score": stmt.excluded.match_score,
            "matched_name": stmt.excluded.matched_name,
            "candidate_unps": stmt.excluded.candidate_unps,
            "raw_json": stmt.excluded.raw_json,
            "last_seen_at": stmt.excluded.last_seen_at,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    db.execute(stmt)


def import_export_by_json(
    db: Any,
    json_path: Path,
    batch_size: int = 500,
    dry_run: bool = False,
    use_fuzzy: bool = False,
    country: str | None = "Беларусь",
    report_path: Path | None = None,
    unmatched_output: Path | None = None,
    progress: Callable[[int, dict[str, int]], None] | None = None,
    progress_every: int = 500,
    limit: int | None = None,
) -> dict[str, int]:
    rows = json.loads(json_path.read_text(encoding="utf-8-sig"))
    if not isinstance(rows, list):
        raise ValueError("Expected a JSON array of export.by company records")

    stats = {
        "total": 0,
        "processed": 0,
        "skipped_country": 0,
        "invalid_row": 0,
        MATCHED: 0,
        AMBIGUOUS: 0,
        NOT_FOUND: 0,
        INVALID_NAME: 0,
        "saved": 0,
    }
    report_rows: list[dict[str, Any]] = []
    pg_trgm_available = _has_pg_trgm(db) if use_fuzzy else False
    pending = 0
    for source_row in rows:
        if limit is not None and stats["processed"] >= limit:
            break
        stats["total"] += 1
        if not isinstance(source_row, dict) or source_row.get("id") is None:
            stats["invalid_row"] += 1
            continue
        if country and source_row.get("country") != country:
            stats["skipped_country"] += 1
            continue

        stats["processed"] += 1
        normalized, match = find_company_match_by_name(
            db,
            str(source_row.get("name") or ""),
            use_fuzzy=use_fuzzy,
            pg_trgm_available=pg_trgm_available,
        )
        stats[match.status] = stats.get(match.status, 0) + 1
        if match.status != MATCHED:
            report_rows.append(
                {
                    "export_by_id": source_row.get("id"),
                    "name": source_row.get("name"),
                    "logo": source_row.get("logo"),
                    "description": source_row.get("description"),
                    "country": source_row.get("country"),
                    "normalized_name": normalized,
                    "match_status": match.status,
                    "match_method": match.method,
                    "candidates": match.candidate_json,
                    "raw_json": source_row,
                }
            )
        if not dry_run:
            upsert_export_by_record(db, source_row, normalized, match)
            stats["saved"] += 1
            pending += 1
            if pending >= batch_size:
                db.commit()
                pending = 0
        if progress and progress_every > 0 and stats["processed"] % progress_every == 0:
            progress(stats["processed"], stats)

    if dry_run:
        db.rollback()
    elif pending:
        db.commit()
    if report_path:
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_payload = {"stats": stats, "rows": report_rows}
            report_path.write_text(
                json.dumps(report_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Failed to write export.by import report to %s: %s", report_path, exc)
            stats["report_write_error"] = 1
    if unmatched_output:
        try:
            unmatched_output.parent.mkdir(parents=True, exist_ok=True)
            unmatched_output.write_text(
                json.dumps(report_rows, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            stats["unmatched_output"] = str(unmatched_output)
        except OSError as exc:
            logger.warning("Failed to write export.by unmatched rows to %s: %s", unmatched_output, exc)
            stats["unmatched_write_error"] = 1
    return stats
