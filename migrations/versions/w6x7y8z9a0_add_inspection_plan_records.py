"""add inspection plan records

Revision ID: w6x7y8z9a0
Revises: v5w6x7y8z9
Create Date: 2026-06-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "w6x7y8z9a0"
down_revision = "v5w6x7y8z9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inspection_plan_records",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("egr_companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("subject_unp", sa.BigInteger(), nullable=False),
        sa.Column("subject_name", sa.Text(), nullable=False),
        sa.Column("plan_period", sa.String(length=16), nullable=False),
        sa.Column("plan_year", sa.Integer(), nullable=True),
        sa.Column("plan_half", sa.Integer(), nullable=True),
        sa.Column("source_region", sa.Text(), nullable=False),
        sa.Column("plan_title", sa.Text(), nullable=True),
        sa.Column("plan_item_no", sa.Integer(), nullable=True),
        sa.Column("approving_authority", sa.Text(), nullable=True),
        sa.Column("controller_unp", sa.BigInteger(), nullable=True),
        sa.Column("controller_authority", sa.Text(), nullable=True),
        sa.Column("executor_phone", sa.Text(), nullable=True),
        sa.Column("start_month", sa.String(length=32), nullable=True),
        sa.Column("start_month_no", sa.Integer(), nullable=True),
        sa.Column("source_file", sa.Text(), nullable=False),
        sa.Column("source_sheet", sa.Text(), nullable=False),
        sa.Column("source_row_no", sa.Integer(), nullable=False),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sync_key", sa.String(length=64), nullable=False),
        sa.Column("sync_hash", sa.String(length=64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("sync_key", name="uq_inspection_plan_records_sync_key"),
    )
    op.create_index("idx_inspection_plan_records_company_id", "inspection_plan_records", ["company_id"])
    op.create_index("idx_inspection_plan_records_subject_unp", "inspection_plan_records", ["subject_unp"])
    op.create_index("idx_inspection_plan_records_plan_period", "inspection_plan_records", ["plan_period"])
    op.create_index("idx_inspection_plan_records_plan_year", "inspection_plan_records", ["plan_year"])
    op.create_index("idx_inspection_plan_records_plan_half", "inspection_plan_records", ["plan_half"])
    op.create_index("idx_inspection_plan_records_source_region", "inspection_plan_records", ["source_region"])
    op.create_index("idx_inspection_plan_records_plan_item_no", "inspection_plan_records", ["plan_item_no"])
    op.create_index("idx_inspection_plan_records_controller_unp", "inspection_plan_records", ["controller_unp"])
    op.create_index("idx_inspection_plan_records_start_month", "inspection_plan_records", ["start_month"])
    op.create_index("idx_inspection_plan_records_start_month_no", "inspection_plan_records", ["start_month_no"])
    op.create_index("idx_inspection_plan_records_last_seen_at", "inspection_plan_records", ["last_seen_at"])


def downgrade():
    op.drop_index("idx_inspection_plan_records_last_seen_at", table_name="inspection_plan_records")
    op.drop_index("idx_inspection_plan_records_start_month_no", table_name="inspection_plan_records")
    op.drop_index("idx_inspection_plan_records_start_month", table_name="inspection_plan_records")
    op.drop_index("idx_inspection_plan_records_controller_unp", table_name="inspection_plan_records")
    op.drop_index("idx_inspection_plan_records_plan_item_no", table_name="inspection_plan_records")
    op.drop_index("idx_inspection_plan_records_source_region", table_name="inspection_plan_records")
    op.drop_index("idx_inspection_plan_records_plan_half", table_name="inspection_plan_records")
    op.drop_index("idx_inspection_plan_records_plan_year", table_name="inspection_plan_records")
    op.drop_index("idx_inspection_plan_records_plan_period", table_name="inspection_plan_records")
    op.drop_index("idx_inspection_plan_records_subject_unp", table_name="inspection_plan_records")
    op.drop_index("idx_inspection_plan_records_company_id", table_name="inspection_plan_records")
    op.drop_table("inspection_plan_records")
