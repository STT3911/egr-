"""Bounded comparison of a registry state snapshot against PostgreSQL."""
from sqlalchemy import text

SQL_BATCH_SIZE = 1000


def find_state_targets(db, unps, state, *, limit, seen):
    """Retain only the enqueue budget; never send a whole registry as SQL args.

    The next scheduled scan starts again and finds the remaining delta after
    the queued companies have been refreshed. No completeness cursor is moved.
    """
    if limit <= 0:
        return []
    targets = []
    for offset in range(0, len(unps), SQL_BATCH_SIZE):
        batch = list(dict.fromkeys(int(u) for u in unps[offset:offset + SQL_BATCH_SIZE]))
        rows = db.execute(text("""
            SELECT api.unp
            FROM unnest(CAST(:unps AS bigint[])) AS api(unp)
            WHERE NOT EXISTS (
                SELECT 1 FROM egr_raw_company_data r WHERE r.unp = api.unp
            ) OR NOT EXISTS (
                SELECT 1 FROM egr_companies c
                WHERE c.unp = api.unp AND c.current_status_code = :state
            )
        """), {"unps": batch, "state": state}).fetchall()
        for (unp,) in rows:
            if unp not in seen:
                seen.add(unp)
                targets.append(unp)
                if len(targets) >= limit:
                    return targets
    return targets
