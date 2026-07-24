"""Persistent scan planning and result tracking for checksum-valid UNPs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import text

from app.core.database import SessionLocal
from app.services.unp_enum import build_unp


SEQ_MAX = 9_999_999


@dataclass(frozen=True)
class IssuanceRange:
    region: int
    seq_start: int
    seq_end: int
    first_unp: int
    last_unp: int
    known_count: int
    scan_start: int
    scan_end: int


def sync_known_candidates() -> int:
    """Mark every UNP already represented by a successful EGR or GRP record."""
    sources = (
        (
            "SELECT unp FROM egr_companies WHERE source = 'egr'",
            "found",
            "pending",
        ),
        (
            """
            SELECT unp
            FROM egr_raw_company_data
            WHERE (data IS NOT NULL OR base_info IS NOT NULL)
              AND processed_at IS NOT NULL
              AND last_error IS NULL
            """,
            "found",
            "pending",
        ),
        (
            "SELECT unp FROM grp_taxpayer_data",
            "pending",
            "found",
        ),
        (
            """
            SELECT unp
            FROM grp_raw_data
            WHERE http_status = 200
              AND raw_json <> '{}'::jsonb
            """,
            "pending",
            "found",
        ),
        (
            "SELECT unp FROM egr_companies WHERE source = 'grp'",
            "pending",
            "found",
        ),
    )
    statement_template = """
        WITH known AS (
            {source_sql}
        ),
        valid AS (
            SELECT unp
            FROM known
            WHERE unp BETWEEN 100000000 AND 999999999
              AND left(unp::text, 1)::integer BETWEEN 1 AND 7
              AND mod(
                    substring(unp::text, 1, 1)::integer * 29
                  + substring(unp::text, 2, 1)::integer * 23
                  + substring(unp::text, 3, 1)::integer * 19
                  + substring(unp::text, 4, 1)::integer * 17
                  + substring(unp::text, 5, 1)::integer * 13
                  + substring(unp::text, 6, 1)::integer * 7
                  + substring(unp::text, 7, 1)::integer * 5
                  + substring(unp::text, 8, 1)::integer * 3,
                    11
              ) = right(unp::text, 1)::integer
        )
        INSERT INTO unp_scan_candidates (
            unp,
            region,
            sequence,
            checksum_valid,
            known_in_db,
            egr_status,
            grp_status,
            overall_status,
            created_at,
            updated_at
        )
        SELECT
            unp,
            left(unp::text, 1)::smallint,
            ((unp / 10) % 10000000)::integer,
            true,
            true,
            :egr_status,
            :grp_status,
            'found',
            now(),
            now()
        FROM valid
        ON CONFLICT (unp) DO UPDATE SET
            known_in_db = true,
            egr_status = CASE
                WHEN EXCLUDED.egr_status = 'found' THEN 'found'
                ELSE unp_scan_candidates.egr_status
            END,
            grp_status = CASE
                WHEN EXCLUDED.grp_status = 'found' THEN 'found'
                ELSE unp_scan_candidates.grp_status
            END,
            overall_status = 'found',
            last_error = NULL,
            updated_at = now()
        WHERE unp_scan_candidates.known_in_db = false
           OR (
                EXCLUDED.egr_status = 'found'
                AND unp_scan_candidates.egr_status <> 'found'
           )
           OR (
                EXCLUDED.grp_status = 'found'
                AND unp_scan_candidates.grp_status <> 'found'
           )
    """
    db = SessionLocal()
    try:
        changed = 0
        for source_sql, egr_status, grp_status in sources:
            result = db.execute(
                text(statement_template.format(source_sql=source_sql)),
                {
                    "egr_status": egr_status,
                    "grp_status": grp_status,
                },
            )
            changed += max(0, int(result.rowcount or 0))
        db.commit()
        return changed
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def refresh_issuance_ranges(
    *,
    gap_limit: int,
    frontier_backtrack: int,
    frontier_lookahead: int,
) -> int:
    """Rebuild dense issuance islands inferred from UNPs marked as known."""
    gap_limit = max(1, int(gap_limit))
    frontier_backtrack = max(0, int(frontier_backtrack))
    frontier_lookahead = max(1, int(frontier_lookahead))
    statement = text(
        """
        WITH ordered AS (
            SELECT
                unp,
                region,
                sequence,
                lag(sequence) OVER (
                    PARTITION BY region
                    ORDER BY sequence
                ) AS previous_sequence
            FROM unp_scan_candidates
            WHERE known_in_db = true
        ),
        boundaries AS (
            SELECT
                *,
                CASE
                    WHEN previous_sequence IS NULL
                      OR sequence - previous_sequence > :gap_limit
                    THEN 1
                    ELSE 0
                END AS starts_range
            FROM ordered
        ),
        grouped AS (
            SELECT
                *,
                sum(starts_range) OVER (
                    PARTITION BY region
                    ORDER BY sequence
                    ROWS UNBOUNDED PRECEDING
                ) AS range_number
            FROM boundaries
        ),
        ranges AS (
            SELECT
                region,
                min(sequence)::integer AS seq_start,
                max(sequence)::integer AS seq_end,
                min(unp)::bigint AS first_unp,
                max(unp)::bigint AS last_unp,
                count(*)::integer AS known_count
            FROM grouped
            GROUP BY region, range_number
        ),
        ranked AS (
            SELECT
                *,
                row_number() OVER (
                    PARTITION BY region
                    ORDER BY seq_end DESC
                ) = 1 AS is_latest
            FROM ranges
        )
        INSERT INTO unp_issuance_ranges (
            region,
            seq_start,
            seq_end,
            first_unp,
            last_unp,
            known_count,
            gap_limit,
            scan_start,
            scan_end,
            is_latest,
            refreshed_at
        )
        SELECT
            region,
            seq_start,
            seq_end,
            first_unp,
            last_unp,
            known_count,
            :gap_limit,
            greatest(seq_start, seq_end - :frontier_backtrack + 1),
            least(:seq_max, seq_end + :frontier_lookahead),
            is_latest,
            now()
        FROM ranked
        ORDER BY region, seq_start
        """
    )
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM unp_issuance_ranges"))
        result = db.execute(
            statement,
            {
                "gap_limit": gap_limit,
                "frontier_backtrack": frontier_backtrack,
                "frontier_lookahead": frontier_lookahead,
                "seq_max": SEQ_MAX,
            },
        )
        db.commit()
        return max(0, int(result.rowcount or 0))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def prepare_scan_registry(
    *,
    gap_limit: int,
    frontier_backtrack: int,
    frontier_lookahead: int,
    force: bool = False,
    max_age_seconds: float = 86_400,
) -> dict:
    db = SessionLocal()
    try:
        state = (
            db.execute(
                text(
                    """
                    SELECT
                        EXISTS (
                            SELECT 1 FROM unp_scan_candidates LIMIT 1
                        ) AS has_candidates,
                        EXISTS (
                            SELECT 1 FROM unp_issuance_ranges LIMIT 1
                        ) AS has_ranges,
                        EXTRACT(
                            EPOCH FROM (
                                now() - max(refreshed_at)
                            )
                        ) AS range_age_seconds
                    FROM unp_issuance_ranges
                    """
                )
            )
            .mappings()
            .one()
        )
    finally:
        db.close()

    range_age = state["range_age_seconds"]
    preparation_fresh = (
        bool(state["has_candidates"])
        and bool(state["has_ranges"])
        and range_age is not None
        and float(range_age) < max(0.0, float(max_age_seconds))
    )
    if preparation_fresh and not force:
        planned_candidates = plan_latest_range_candidates()
        status = get_registry_status()
        status["synchronized_rows"] = 0
        status["rebuilt_ranges"] = 0
        status["planned_candidates"] = planned_candidates
        status["preparation_skipped"] = True
        status["range_age_seconds"] = int(float(range_age))
        return status

    synchronized = sync_known_candidates()
    ranges = refresh_issuance_ranges(
        gap_limit=gap_limit,
        frontier_backtrack=frontier_backtrack,
        frontier_lookahead=frontier_lookahead,
    )
    planned_candidates = plan_latest_range_candidates()
    status = get_registry_status()
    status["synchronized_rows"] = synchronized
    status["rebuilt_ranges"] = ranges
    status["planned_candidates"] = planned_candidates
    status["preparation_skipped"] = False
    status["range_age_seconds"] = 0
    return status


def get_latest_issuance_range(region: int) -> IssuanceRange | None:
    db = SessionLocal()
    try:
        row = (
            db.execute(
                text(
                    """
                    SELECT
                        region,
                        seq_start,
                        seq_end,
                        first_unp,
                        last_unp,
                        known_count,
                        scan_start,
                        scan_end
                    FROM unp_issuance_ranges
                    WHERE region = :region AND is_latest = true
                    ORDER BY seq_end DESC
                    LIMIT 1
                    """
                ),
                {"region": int(region)},
            )
            .mappings()
            .first()
        )
        return IssuanceRange(**dict(row)) if row else None
    finally:
        db.close()


def plan_candidates(
    candidates: Iterable[str],
    *,
    egr_present: set[int],
    grp_present: set[int],
) -> None:
    rows = []
    for unp_text in candidates:
        unp = int(unp_text)
        has_egr = unp in egr_present
        has_grp = unp in grp_present
        rows.append(
            {
                "unp": unp,
                "region": int(unp_text[0]),
                "sequence": int(unp_text[1:8]),
                "known_in_db": has_egr or has_grp,
                "egr_status": "found" if has_egr else "pending",
                "grp_status": "found" if has_grp else "pending",
                "overall_status": (
                    "found"
                    if has_egr and has_grp
                    else "partial"
                    if has_egr or has_grp
                    else "pending"
                ),
            }
        )
    if not rows:
        return

    statement = text(
        """
        INSERT INTO unp_scan_candidates (
            unp,
            region,
            sequence,
            checksum_valid,
            known_in_db,
            egr_status,
            grp_status,
            overall_status,
            created_at,
            updated_at
        )
        VALUES (
            :unp,
            :region,
            :sequence,
            true,
            :known_in_db,
            :egr_status,
            :grp_status,
            :overall_status,
            now(),
            now()
        )
        ON CONFLICT (unp) DO UPDATE SET
            known_in_db = (
                unp_scan_candidates.known_in_db
                OR EXCLUDED.known_in_db
            ),
            egr_status = CASE
                WHEN EXCLUDED.egr_status = 'found' THEN 'found'
                ELSE unp_scan_candidates.egr_status
            END,
            grp_status = CASE
                WHEN EXCLUDED.grp_status = 'found' THEN 'found'
                ELSE unp_scan_candidates.grp_status
            END,
            overall_status = CASE
                WHEN unp_scan_candidates.overall_status = 'found'
                  OR EXCLUDED.overall_status = 'found'
                THEN 'found'
                WHEN unp_scan_candidates.known_in_db
                  OR EXCLUDED.known_in_db
                THEN 'partial'
                ELSE unp_scan_candidates.overall_status
            END,
            updated_at = now()
        """
    )
    db = SessionLocal()
    try:
        db.execute(statement, rows)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def plan_latest_range_candidates() -> int:
    """Create pending rows for every checksum-valid candidate in frontier windows."""
    db = SessionLocal()
    try:
        ranges = (
            db.execute(
                text(
                    """
                    SELECT region, scan_start, scan_end
                    FROM unp_issuance_ranges
                    WHERE is_latest = true
                    ORDER BY region
                    """
                )
            )
            .mappings()
            .all()
        )
    finally:
        db.close()

    candidates = []
    for row in ranges:
        for sequence in range(int(row["scan_start"]), int(row["scan_end"]) + 1):
            unp = build_unp(int(row["region"]), sequence)
            if unp is not None:
                candidates.append(unp)
    plan_candidates(candidates, egr_present=set(), grp_present=set())
    return len(candidates)


def record_probe_results(results: Iterable[object]) -> None:
    rows = []
    for result in results:
        egr_status = "found" if result.egr.status == "skipped" else result.egr.status
        grp_status = "found" if result.grp.status == "skipped" else result.grp.status
        has_found = "found" in {egr_status, grp_status}
        has_error = "error" in {egr_status, grp_status} or bool(
            result.persist_errors
        )
        if has_found and has_error:
            overall_status = "partial"
        elif has_found:
            overall_status = "found"
        elif egr_status == "not_found" and grp_status == "not_found":
            overall_status = "not_found"
        else:
            overall_status = "error"
        rows.append(
            {
                "unp": int(result.unp),
                "known_in_db": has_found,
                "egr_status": egr_status,
                "grp_status": grp_status,
                "overall_status": overall_status,
                "last_error": result.error or None,
            }
        )
    if not rows:
        return

    statement = text(
        """
        UPDATE unp_scan_candidates
        SET
            known_in_db = known_in_db OR :known_in_db,
            egr_status = :egr_status,
            grp_status = :grp_status,
            overall_status = :overall_status,
            attempts = attempts + 1,
            first_checked_at = COALESCE(first_checked_at, now()),
            last_checked_at = now(),
            next_check_at = NULL,
            last_error = :last_error,
            updated_at = now()
        WHERE unp = :unp
        """
    )
    db = SessionLocal()
    try:
        db.execute(statement, rows)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_registry_status() -> dict:
    db = SessionLocal()
    try:
        counts = (
            db.execute(
                text(
                    """
                    SELECT
                        count(*)::bigint AS candidates,
                        count(*) FILTER (
                            WHERE known_in_db = true
                        )::bigint AS known,
                        count(*) FILTER (
                            WHERE overall_status = 'pending'
                        )::bigint AS pending,
                        count(*) FILTER (
                            WHERE overall_status = 'not_found'
                        )::bigint AS not_found,
                        count(*) FILTER (
                            WHERE overall_status = 'partial'
                        )::bigint AS partial,
                        count(*) FILTER (
                            WHERE overall_status = 'error'
                        )::bigint AS errors
                    FROM unp_scan_candidates
                    """
                )
            )
            .mappings()
            .one()
        )
        latest_ranges = (
            db.execute(
                text(
                    """
                    SELECT
                        region,
                        seq_start,
                        seq_end,
                        first_unp,
                        last_unp,
                        known_count,
                        scan_start,
                        scan_end
                    FROM unp_issuance_ranges
                    WHERE is_latest = true
                    ORDER BY region
                    """
                )
            )
            .mappings()
            .all()
        )
        range_count = db.execute(
            text("SELECT count(*) FROM unp_issuance_ranges")
        ).scalar_one()
        return {
            **{key: int(value or 0) for key, value in counts.items()},
            "ranges": int(range_count or 0),
            "latest_ranges": [dict(row) for row in latest_ranges],
        }
    finally:
        db.close()
