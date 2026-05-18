"""add trade registry admin imports

Revision ID: n7o8p9q0r1
Revises: m6n7o8p9q0, 9b9e1f71f6cf
Create Date: 2026-05-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "n7o8p9q0r1"
down_revision = ("m6n7o8p9q0", "9b9e1f71f6cf")
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "trade_registry_import_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("stored_path", sa.Text(), nullable=False),
        sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column("stats_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_trade_registry_import_runs_status", "trade_registry_import_runs", ["status"])
    op.create_index("idx_trade_registry_import_runs_source_date", "trade_registry_import_runs", ["source_date"])

    op.create_table(
        "trade_registry_import_stage",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trade_registry_import_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("unp", sa.BigInteger(), nullable=False),
        sa.Column("registration_number", sa.String(length=64), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("egr_companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sync_hash", sa.String(length=64), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("run_id", "unp", "registration_number", name="uq_trade_registry_import_stage_run_unp_reg"),
    )
    op.create_index("idx_trade_registry_import_stage_run_id", "trade_registry_import_stage", ["run_id"])
    op.create_index("idx_trade_registry_import_stage_unp", "trade_registry_import_stage", ["unp"])
    op.create_index("idx_trade_registry_import_stage_company_id", "trade_registry_import_stage", ["company_id"])


def downgrade():
    op.drop_index("idx_trade_registry_import_stage_company_id", table_name="trade_registry_import_stage")
    op.drop_index("idx_trade_registry_import_stage_unp", table_name="trade_registry_import_stage")
    op.drop_index("idx_trade_registry_import_stage_run_id", table_name="trade_registry_import_stage")
    op.drop_table("trade_registry_import_stage")
    op.drop_index("idx_trade_registry_import_runs_source_date", table_name="trade_registry_import_runs")
    op.drop_index("idx_trade_registry_import_runs_status", table_name="trade_registry_import_runs")
    op.drop_table("trade_registry_import_runs")
