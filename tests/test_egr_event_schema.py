"""Regression for audit columns absent in databases built from migrations."""
import ast
import importlib.util
import re
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql

from app.crud.company import CompanyCRUD
from app.database.models import CompanyEvent

ROOT = Path(__file__).resolve().parents[1]


def load_migration():
    spec = importlib.util.spec_from_file_location(
        "event_timestamps_test", ROOT / "migrations/versions/egrapi3_event_timestamps.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def migration_sql():
    output = StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={
        "as_sql": True, "output_buffer": output,
    })
    module = load_migration()
    module.op = Operations(context)
    module.upgrade()
    return output.getvalue()


def original_event_columns():
    # Read the real historical migration, not ORM create_all (which concealed
    # this bug by silently supplying the two missing columns in fresh tests).
    path = ROOT / "migrations/versions/b2c3d4e5f6g7_add_missing_reference_tables_and_events.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    create = next(node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_table" and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "egr_company_events")
    return {arg.args[0].value for arg in create.args[1:]
            if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute)
            and arg.func.attr == "Column"}


def test_migrated_column_set_matches_event_model_and_conflict_update():
    original = original_event_columns()
    assert "updated_at" not in original and "created_at" not in original
    added = set(re.findall(r"ADD COLUMN IF NOT EXISTS (\w+)", migration_sql()))
    actual = original | added
    assert actual == set(CompanyEvent.__table__.columns.keys())
    db = Mock()
    CompanyCRUD(db)._save_egr_events(SimpleNamespace(id=uuid4()), [{
        "event_record_id": 16693525500, "notes": "Updated event",
    }])
    statement = db.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT" in sql and "updated_at = now()" in sql
    conflict_columns = {
        key.name if hasattr(key, "name") else key
        for key, _ in statement._post_values_clause.update_values_to_set
    }
    assert conflict_columns <= actual


def test_timestamp_migration_preserves_existing_values_and_unknown_old_dates():
    sql = migration_sql()
    adds = [line for line in sql.splitlines() if "ADD COLUMN" in line]
    assert len(adds) == 2
    assert all("IF NOT EXISTS" in line and "NULL" in line and "DEFAULT" not in line for line in adds)
    assert sql.count("SET DEFAULT now()") == 2
    assert not re.search(r"\b(UPDATE|DELETE|DROP|TRUNCATE)\b", sql)


def test_downgrade_never_drops_preexisting_audit_columns():
    module = load_migration()
    module.op = Mock()
    with pytest.raises(RuntimeError, match="retained for safety"):
        module.downgrade()
    module.op.execute.assert_not_called()
