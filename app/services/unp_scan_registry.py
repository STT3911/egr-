"""Persistent scan planning and result tracking for checksum-valid UNPs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

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


@dataclass(frozen=True)
class RangeScanRun:
    id: int
    cycle_number: int
    region: int
    source_seq_start: int
    source_seq_end: int
    scan_start: int
    scan_end: int
    next_sequence: int
    status: str


def _frontier_scan_bounds(
    issuance_range: Mapping[str, object],
    *,
    seq_start: int,
    seq_end: int,
) -> tuple[int, int]:
    """Clamp a persisted frontier window to the configured sequence bounds."""
    return (
        max(int(seq_start), int(issuance_range["scan_start"])),
        min(int(seq_end), int(issuance_range["scan_end"])),
    )


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
            CASE
                WHEN :egr_status = 'found' AND :grp_status = 'found'
                THEN 'found'
                ELSE 'partial'
            END,
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
            overall_status = CASE
                WHEN (
                    unp_scan_candidates.egr_status = 'found'
                    OR EXCLUDED.egr_status = 'found'
                ) AND (
                    unp_scan_candidates.grp_status = 'found'
                    OR EXCLUDED.grp_status = 'found'
                )
                THEN 'found'
                ELSE 'partial'
            END,
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


def ensure_range_scan_cycle(
    *,
    regions: Iterable[int],
    seq_start: int,
    seq_end: int,
    gap_limit: int,
    frontier_backtrack: int,
    frontier_lookahead: int,
) -> dict:
    """Resume an unfinished frontier cycle or create the next one.

    Frontier cycles contain only the latest issuance island for each region and
    use its narrow ``scan_start``/``scan_end`` window.  Older versions created
    one run for every historical island; those unfinished cycles are retired
    here so a deployment cannot resume the expensive legacy scan.
    """
    selected_regions = sorted({int(region) for region in regions})
    if not selected_regions:
        raise ValueError("At least one region is required")

    repaired_legacy_ranges = 0
    db = SessionLocal()
    try:
        active_cycle = db.execute(
            text(
                """
                SELECT min(cycle_number)
                FROM unp_range_scan_runs
                WHERE status IN ('pending', 'running', 'error')
                  AND region = ANY(:regions)
                """
            ),
            {"regions": selected_regions},
        ).scalar()
        if active_cycle is not None:
            legacy_cycle = bool(
                db.execute(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM unp_range_scan_runs AS run
                            LEFT JOIN unp_issuance_ranges AS issuance
                              ON issuance.region = run.region
                             AND issuance.is_latest = true
                             AND issuance.seq_start = run.source_seq_start
                             AND issuance.seq_end = run.source_seq_end
                            WHERE run.cycle_number = :cycle_number
                              AND run.region = ANY(:regions)
                              AND run.status IN ('pending', 'running', 'error')
                              AND (
                                  issuance.id IS NULL
                                  OR run.scan_start <> greatest(
                                      :seq_start,
                                      issuance.scan_start
                                  )
                                  OR run.scan_end <> least(
                                      :seq_end,
                                      issuance.scan_end
                                  )
                              )
                        )
                        """
                    ),
                    {
                        "cycle_number": int(active_cycle),
                        "regions": selected_regions,
                        "seq_start": int(seq_start),
                        "seq_end": int(seq_end),
                    },
                ).scalar()
            )
            if not legacy_cycle:
                return get_range_scan_cycle_status(int(active_cycle))

            result = db.execute(
                text(
                    """
                    UPDATE unp_range_scan_runs
                    SET
                        status = 'completed',
                        completed_at = COALESCE(completed_at, now()),
                        updated_at = now()
                    WHERE cycle_number = :cycle_number
                      AND region = ANY(:regions)
                      AND status IN ('pending', 'running', 'error')
                    """
                ),
                {
                    "cycle_number": int(active_cycle),
                    "regions": selected_regions,
                },
            )
            repaired_legacy_ranges = max(0, int(result.rowcount or 0))
            db.commit()

        previous_cycle = db.execute(
            text("SELECT max(cycle_number) FROM unp_range_scan_runs")
        ).scalar()
    finally:
        db.close()

    db = SessionLocal()
    try:
        ranges = (
            db.execute(
                text(
                    """
                    SELECT
                        id,
                        region,
                        seq_start,
                        seq_end,
                        scan_start,
                        scan_end
                    FROM unp_issuance_ranges
                    WHERE region = ANY(:regions)
                      AND is_latest = true
                      AND scan_end >= :seq_start
                      AND scan_start <= :seq_end
                    ORDER BY region, seq_start
                    """
                ),
                {
                    "regions": selected_regions,
                    "seq_start": int(seq_start),
                    "seq_end": int(seq_end),
                },
            )
            .mappings()
            .all()
        )
        if not ranges:
            raise RuntimeError("No UNP issuance ranges available for scanning")

        cycle_number = int(previous_cycle or 0) + 1
        rows = []
        for item in ranges:
            range_scan_start, range_scan_end = _frontier_scan_bounds(
                item,
                seq_start=seq_start,
                seq_end=seq_end,
            )
            if range_scan_start > range_scan_end:
                continue
            rows.append(
                {
                    "cycle_number": cycle_number,
                    "source_range_id": int(item["id"]),
                    "region": int(item["region"]),
                    "source_seq_start": int(item["seq_start"]),
                    "source_seq_end": int(item["seq_end"]),
                    "scan_start": range_scan_start,
                    "scan_end": range_scan_end,
                    "next_sequence": range_scan_start,
                }
            )
        if not rows:
            raise RuntimeError(
                "No UNP issuance ranges overlap the configured scan bounds"
            )

        db.execute(
            text(
                """
                INSERT INTO unp_range_scan_runs (
                    cycle_number,
                    source_range_id,
                    region,
                    source_seq_start,
                    source_seq_end,
                    scan_start,
                    scan_end,
                    next_sequence,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (
                    :cycle_number,
                    :source_range_id,
                    :region,
                    :source_seq_start,
                    :source_seq_end,
                    :scan_start,
                    :scan_end,
                    :next_sequence,
                    'pending',
                    now(),
                    now()
                )
                """
            ),
            rows,
        )
        db.commit()
        status = get_range_scan_cycle_status(cycle_number)
        status["repaired_legacy_ranges"] = repaired_legacy_ranges
        return status
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def claim_next_range_scan(cycle_number: int) -> RangeScanRun | None:
    """Atomically claim or resume the next unfinished range in a cycle."""
    db = SessionLocal()
    try:
        row = (
            db.execute(
                text(
                    """
                    WITH next_range AS (
                        SELECT id
                        FROM unp_range_scan_runs
                        WHERE cycle_number = :cycle_number
                          AND status IN ('pending', 'running', 'error')
                        ORDER BY
                            CASE WHEN status = 'running' THEN 0 ELSE 1 END,
                            region,
                            scan_start
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE unp_range_scan_runs AS target
                    SET
                        status = 'running',
                        started_at = COALESCE(started_at, now()),
                        updated_at = now()
                    FROM next_range
                    WHERE target.id = next_range.id
                    RETURNING
                        target.id,
                        target.cycle_number,
                        target.region,
                        target.source_seq_start,
                        target.source_seq_end,
                        target.scan_start,
                        target.scan_end,
                        target.next_sequence,
                        target.status
                    """
                ),
                {"cycle_number": int(cycle_number)},
            )
            .mappings()
            .first()
        )
        db.commit()
        return RangeScanRun(**dict(row)) if row else None
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def update_range_scan_progress(
    range_scan_id: int,
    *,
    next_sequence: int,
    first_checked_unp: int | None,
    last_checked_unp: int | None,
    checked_count: int,
    found_count: int,
    not_found_count: int,
    error_count: int,
) -> None:
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                UPDATE unp_range_scan_runs
                SET
                    next_sequence = :next_sequence,
                    first_checked_unp = COALESCE(
                        first_checked_unp,
                        :first_checked_unp
                    ),
                    last_checked_unp = COALESCE(
                        :last_checked_unp,
                        last_checked_unp
                    ),
                    checked_count = checked_count + :checked_count,
                    found_count = found_count + :found_count,
                    not_found_count = not_found_count + :not_found_count,
                    error_count = error_count + :error_count,
                    status = 'running',
                    updated_at = now()
                WHERE id = :range_scan_id
                """
            ),
            {
                "range_scan_id": int(range_scan_id),
                "next_sequence": int(next_sequence),
                "first_checked_unp": first_checked_unp,
                "last_checked_unp": last_checked_unp,
                "checked_count": int(checked_count),
                "found_count": int(found_count),
                "not_found_count": int(not_found_count),
                "error_count": int(error_count),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def complete_range_scan(range_scan_id: int) -> None:
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                UPDATE unp_range_scan_runs
                SET
                    status = 'completed',
                    next_sequence = scan_end + 1,
                    completed_at = now(),
                    updated_at = now()
                WHERE id = :range_scan_id
                """
            ),
            {"range_scan_id": int(range_scan_id)},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_range_scan_cycle_status(cycle_number: int | None = None) -> dict:
    db = SessionLocal()
    try:
        selected_cycle = cycle_number
        if selected_cycle is None:
            selected_cycle = db.execute(
                text("SELECT max(cycle_number) FROM unp_range_scan_runs")
            ).scalar()
        if selected_cycle is None:
            return {
                "cycle_number": 0,
                "ranges": 0,
                "completed_ranges": 0,
                "pending_ranges": 0,
                "checked": 0,
                "found": 0,
                "not_found": 0,
                "errors": 0,
                "current_range": None,
            }

        totals = (
            db.execute(
                text(
                    """
                    SELECT
                        count(*)::bigint AS ranges,
                        count(*) FILTER (
                            WHERE status = 'completed'
                        )::bigint AS completed_ranges,
                        count(*) FILTER (
                            WHERE status <> 'completed'
                        )::bigint AS pending_ranges,
                        coalesce(sum(checked_count), 0)::bigint AS checked,
                        coalesce(sum(found_count), 0)::bigint AS found,
                        coalesce(sum(not_found_count), 0)::bigint AS not_found,
                        coalesce(sum(error_count), 0)::bigint AS errors
                    FROM unp_range_scan_runs
                    WHERE cycle_number = :cycle_number
                    """
                ),
                {"cycle_number": int(selected_cycle)},
            )
            .mappings()
            .one()
        )
        current = (
            db.execute(
                text(
                    """
                    SELECT
                        id,
                        region,
                        source_seq_start,
                        source_seq_end,
                        scan_start,
                        scan_end,
                        next_sequence,
                        first_checked_unp,
                        last_checked_unp,
                        status,
                        checked_count,
                        found_count,
                        not_found_count,
                        error_count
                    FROM unp_range_scan_runs
                    WHERE cycle_number = :cycle_number
                      AND status <> 'completed'
                    ORDER BY
                        CASE WHEN status = 'running' THEN 0 ELSE 1 END,
                        region,
                        scan_start
                    LIMIT 1
                    """
                ),
                {"cycle_number": int(selected_cycle)},
            )
            .mappings()
            .first()
        )
        return {
            "cycle_number": int(selected_cycle),
            **{key: int(value or 0) for key, value in totals.items()},
            "current_range": dict(current) if current else None,
        }
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
                WHEN (
                    unp_scan_candidates.egr_status = 'found'
                    OR EXCLUDED.egr_status = 'found'
                ) AND (
                    unp_scan_candidates.grp_status = 'found'
                    OR EXCLUDED.grp_status = 'found'
                )
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


def get_due_probe_candidates(
    candidates: Iterable[str],
    *,
    not_found_recheck_seconds: float,
    partial_recheck_seconds: float,
) -> set[str]:
    """Return candidates whose missing source data is due for verification."""
    candidate_values = [int(unp) for unp in candidates]
    if not candidate_values:
        return set()

    statement = text(
        """
        SELECT unp
        FROM unp_scan_candidates
        WHERE unp = ANY(:unps)
          AND (
              last_checked_at IS NULL
              OR (
                  overall_status = 'error'
                  AND (
                      next_check_at IS NULL
                      OR next_check_at <= now()
                  )
              )
              OR (
                  overall_status = 'not_found'
                  AND COALESCE(
                      next_check_at,
                      last_checked_at
                        + (:not_found_recheck_seconds * interval '1 second')
                  ) <= now()
              )
              OR (
                  (
                      overall_status = 'partial'
                      OR overall_status = 'found'
                         AND (egr_status <> 'found' OR grp_status <> 'found')
                  )
                  AND COALESCE(
                      next_check_at,
                      last_checked_at
                        + (:partial_recheck_seconds * interval '1 second')
                  ) <= now()
              )
          )
        """
    )
    db = SessionLocal()
    try:
        rows = db.execute(
            statement,
            {
                "unps": candidate_values,
                "not_found_recheck_seconds": max(
                    0.0,
                    float(not_found_recheck_seconds),
                ),
                "partial_recheck_seconds": max(
                    0.0,
                    float(partial_recheck_seconds),
                ),
            },
        )
        return {str(int(unp)) for (unp,) in rows}
    finally:
        db.close()


def _probe_result_state(result: object) -> tuple[str, str, str, bool]:
    """Map a dual-source result to persistent per-source verification state."""
    egr_status = "found" if result.egr.status == "skipped" else result.egr.status
    grp_status = "found" if result.grp.status == "skipped" else result.grp.status
    for error in result.persist_errors:
        if error.startswith("EGR persist:"):
            egr_status = "error"
        elif error.startswith("GRP persist:"):
            grp_status = "error"

    statuses = {egr_status, grp_status}
    both_found = egr_status == "found" and grp_status == "found"
    has_found = "found" in statuses
    has_error = "error" in statuses
    if both_found:
        overall_status = "found"
    elif has_found:
        overall_status = "partial"
    elif statuses == {"not_found"}:
        overall_status = "not_found"
    elif has_error:
        overall_status = "error"
    else:
        overall_status = "pending"
    return egr_status, grp_status, overall_status, has_found


def record_probe_results(
    results: Iterable[object],
    *,
    not_found_recheck_seconds: float = 86_400,
    partial_recheck_seconds: float = 86_400,
    error_recheck_seconds: float = 300,
) -> None:
    rows = []
    for result in results:
        egr_status, grp_status, overall_status, has_found = (
            _probe_result_state(result)
        )
        recheck_seconds = (
            0
            if result.persist_errors
            else not_found_recheck_seconds
            if overall_status == "not_found"
            else partial_recheck_seconds
            if overall_status == "partial"
            else error_recheck_seconds
            if overall_status == "error"
            else None
        )
        rows.append(
            {
                "unp": int(result.unp),
                "known_in_db": has_found,
                "egr_status": egr_status,
                "grp_status": grp_status,
                "overall_status": overall_status,
                "recheck_seconds": recheck_seconds,
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
            next_check_at = CASE
                WHEN :recheck_seconds IS NULL THEN NULL
                ELSE now() + (
                    CAST(:recheck_seconds AS double precision)
                    * interval '1 second'
                )
            END,
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
