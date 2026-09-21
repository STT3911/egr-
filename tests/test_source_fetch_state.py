from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.database.models import SourceFetchAttempt
from app.services.source_fetch_state import select_due_unps, record_attempt

NOW = datetime(2026, 9, 14, 12)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    SourceFetchAttempt.__table__.create(engine)
    with Session(engine) as session:
        session.execute(text("CREATE TABLE egr_companies (unp BIGINT PRIMARY KEY)"))
        for table in ("egr_company_place_locations", "grp_taxpayer_data"):
            session.execute(text(f"CREATE TABLE {table} (unp BIGINT PRIMARY KEY, fetched_at TIMESTAMP)"))
        session.execute(text("INSERT INTO egr_companies (unp) VALUES (:unp)"), [{"unp": u} for u in range(1, 21)])
        session.commit()
        yield session
    engine.dispose()


@pytest.mark.parametrize("source", ["grp", "place_locations"])
def test_empty_low_unps_do_not_block_next_batch(db, source):
    first = select_due_unps(db, source, 5, 30, NOW)
    assert first == [1, 2, 3, 4, 5]
    for unp in first:
        record_attempt(db, source, unp, "empty", refresh_days=30, now=NOW)
    db.commit()
    assert select_due_unps(db, source, 5, 30, NOW + timedelta(days=1)) == [6, 7, 8, 9, 10]
    assert db.execute(text("SELECT count(*) FROM egr_company_place_locations")).scalar() == 0


def test_due_retries_do_not_starve_unseen_and_stale_rows(db):
    for unp in range(1, 6):
        record_attempt(db, "grp", unp, "error", refresh_days=30, now=NOW - timedelta(days=1))
    db.execute(text("INSERT INTO grp_taxpayer_data VALUES (20, :date)"), {"date": NOW - timedelta(days=90)})
    db.commit()
    candidates = select_due_unps(db, "grp", 6, 30, NOW)
    assert len(candidates) == len(set(candidates)) == 6
    assert 20 in candidates
    assert any(6 <= unp <= 19 for unp in candidates)
    assert any(unp <= 5 for unp in candidates)


def test_fresh_records_are_not_refetched(db):
    db.execute(text("INSERT INTO grp_taxpayer_data VALUES (1, :date)"), {"date": NOW})
    assert 1 not in select_due_unps(db, "grp", 20, 30, NOW)


def test_short_error_cooldown_and_long_empty_cooldown(db):
    record_attempt(db, "place_locations", 1, "error", refresh_days=90, error_minutes=60, now=NOW)
    record_attempt(db, "place_locations", 2, "empty", refresh_days=90, empty_days=7, now=NOW)
    db.commit()
    rows = {row.unp: row for row in db.query(SourceFetchAttempt).all()}
    assert rows[1].next_check_at == NOW + timedelta(hours=1)
    assert rows[2].next_check_at == NOW + timedelta(days=7)
    record_attempt(db, "place_locations", 1, "success", refresh_days=90, now=NOW)
    db.commit()
    assert db.query(SourceFetchAttempt).count() == 2


def test_grp_reparse_updates_real_fetch_timestamp():
    from app.crud.grp import GrpCRUD
    from types import SimpleNamespace
    db = Mock()
    crud = GrpCRUD(db)
    raw = SimpleNamespace(raw_json={"VUNP": 100000001, "VNAIMP": "Example"}, updated_at=NOW)
    crud.get_raw_by_unp = lambda _: raw
    crud.get_by_unp = lambda _: None
    crud.parse_from_raw(100000001)
    statement = db.execute.call_args.args[0]
    assert statement.compile().params["fetched_at"] == NOW
    assert raw.parsed is True
