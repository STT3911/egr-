"""Offline PostgreSQL DDL and isolated SQLite constraint checks; no external DB."""
import importlib.util
import io
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles, deregister

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/versions/court1schema_add_courts_cases_judgments.py"


def load_migration():
    spec = importlib.util.spec_from_file_location("court_migration_under_test", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_single_head_after_existing_revision():
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["court1schema"]
    assert scripts.get_revision("court1schema").down_revision == "addrunit1"


def test_postgres_ddl_is_additive_and_seeded(monkeypatch):
    migration = load_migration()
    output = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={
        "as_sql": True, "output_buffer": output, "literal_binds": True,
    })
    monkeypatch.setattr(migration, "op", Operations(context))
    migration.upgrade()
    sql = output.getvalue()
    assert sql.count("CREATE TABLE ") == 3
    assert sql.count("INSERT INTO courts ") == 8
    assert "BIGSERIAL" in sql and "JSONB" in sql and "TIMESTAMP WITH TIME ZONE" in sql
    assert "ON DELETE RESTRICT" in sql
    assert "DROP " not in sql and "ALTER TABLE " not in sql


@pytest.fixture
def migrated_db(monkeypatch):
    # SQLite is used only to exercise rows/constraints locally. PostgreSQL JSONB
    # compilation is validated separately above. No production URL is used.
    compiles(JSONB, "sqlite")(lambda _type, _compiler, **_kw: "JSON")
    engine = sa.create_engine("sqlite://")
    migration = load_migration()
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
            migration.upgrade()
            yield connection, migration
    finally:
        engine.dispose()
        deregister(JSONB)


def test_seed_and_two_decisions_per_case(migrated_db):
    connection, _ = migrated_db
    assert connection.scalar(sa.text("SELECT count(*) FROM courts")) == 8
    connection.exec_driver_sql("INSERT INTO court_cases(id,court_id,source_process_id,case_number) VALUES (1,151,100,'same-number')")
    connection.exec_driver_sql("INSERT INTO court_cases(id,court_id,source_process_id,case_number) VALUES (2,152,100,'same-number')")
    connection.exec_driver_sql("INSERT INTO court_judgments(id,case_id,source_document_id) VALUES (1,1,101),(2,1,102)")
    assert connection.scalar(sa.text("SELECT count(*) FROM court_judgments WHERE case_id=1")) == 2
    with pytest.raises(sa.exc.IntegrityError):
        connection.exec_driver_sql("INSERT INTO court_judgments(id,case_id,source_document_id) VALUES (3,1,101)")
    with pytest.raises(sa.exc.IntegrityError):
        connection.exec_driver_sql("INSERT INTO court_cases(id,court_id,source_process_id,case_number) VALUES (3,151,100,'other-number')")
    with pytest.raises(sa.exc.IntegrityError):
        connection.exec_driver_sql("INSERT INTO court_judgments(id,case_id,source_document_id) VALUES (4,999,103)")
    with pytest.raises(sa.exc.IntegrityError):
        connection.exec_driver_sql("DELETE FROM court_cases WHERE id=1")


def test_downgrade_preserves_unrelated_tables_and_can_reupgrade(migrated_db):
    connection, migration = migrated_db
    connection.exec_driver_sql("CREATE TABLE unrelated_test_data (id INTEGER)")
    connection.exec_driver_sql("INSERT INTO unrelated_test_data VALUES (42)")
    migration.downgrade()
    assert connection.scalar(sa.text("SELECT id FROM unrelated_test_data")) == 42
    assert "courts" not in sa.inspect(connection).get_table_names()
    migration.upgrade()
    assert connection.scalar(sa.text("SELECT count(*) FROM courts")) == 8


def test_models_match_migration(migrated_db, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/court_test")
    from app.database.models import Court, CourtCase, CourtJudgmentRecord
    connection, _ = migrated_db
    inspector = sa.inspect(connection)
    for model in (Court, CourtCase, CourtJudgmentRecord):
        table = model.__table__
        columns = inspector.get_columns(table.name)
        assert {column["name"] for column in columns} == set(table.columns.keys())
        assert {c["name"] for c in columns if c["nullable"]} == {
            c.name for c in table.columns if c.nullable
        }
        assert {idx["name"] for idx in inspector.get_indexes(table.name)} == {
            idx.name for idx in table.indexes
        }
