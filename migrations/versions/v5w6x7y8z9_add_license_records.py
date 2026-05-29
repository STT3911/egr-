"""add license.gov.by records

Revision ID: v5w6x7y8z9
Revises: u4v5w6x7y8
Create Date: 2026-05-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "v5w6x7y8z9"
down_revision = "u4v5w6x7y8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "license_records",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("license_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("egr_companies.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("holder_unp", sa.BigInteger(), nullable=True),
        sa.Column("holder_name", sa.Text(), nullable=True),
        sa.Column("generated_number", sa.String(length=64), nullable=True),
        sa.Column("activity_type_id", sa.BigInteger(), nullable=True),
        sa.Column("activity_type_code", sa.String(length=64), nullable=True),
        sa.Column("activity_type_name", sa.Text(), nullable=True),
        sa.Column("activity_date_start", sa.DateTime(), nullable=True),
        sa.Column("activity_date_end", sa.DateTime(), nullable=True),
        sa.Column("activity_is_active", sa.Boolean(), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sync_hash", sa.String(length=64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("license_id", name="uq_license_records_license_id"),
    )
    op.create_index("idx_license_records_license_id", "license_records", ["license_id"])
    op.create_index("idx_license_records_company_id", "license_records", ["company_id"])
    op.create_index("idx_license_records_holder_unp", "license_records", ["holder_unp"])
    op.create_index("idx_license_records_generated_number", "license_records", ["generated_number"])
    op.create_index("idx_license_records_activity_type_id", "license_records", ["activity_type_id"])
    op.create_index("idx_license_records_activity_type_name", "license_records", ["activity_type_name"])
    op.create_index("idx_license_records_activity_is_active", "license_records", ["activity_is_active"])
    op.create_index("idx_license_records_last_seen_at", "license_records", ["last_seen_at"])

    op.create_table(
        "license_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("total_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unchanged_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_page", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("stats_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_license_sync_runs_status", "license_sync_runs", ["status"])


def downgrade():
    op.drop_index("idx_license_sync_runs_status", table_name="license_sync_runs")
    op.drop_table("license_sync_runs")

    op.drop_index("idx_license_records_last_seen_at", table_name="license_records")
    op.drop_index("idx_license_records_activity_is_active", table_name="license_records")
    op.drop_index("idx_license_records_activity_type_name", table_name="license_records")
    op.drop_index("idx_license_records_activity_type_id", table_name="license_records")
    op.drop_index("idx_license_records_generated_number", table_name="license_records")
    op.drop_index("idx_license_records_holder_unp", table_name="license_records")
    op.drop_index("idx_license_records_company_id", table_name="license_records")
    op.drop_index("idx_license_records_license_id", table_name="license_records")
    op.drop_table("license_records")
