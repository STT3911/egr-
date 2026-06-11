"""add egr_raw_company_data retry fields (error_attempts, next_retry_at)

Self-healing ретрай ошибочных raw-строк с backoff и лимитом попыток.

Revision ID: f5g6h7i8j9
Revises: e4f5g6h7i8
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa


revision = "f5g6h7i8j9"
down_revision = "e4f5g6h7i8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "egr_raw_company_data",
        sa.Column("error_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("egr_raw_company_data", sa.Column("next_retry_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_egr_raw_retry_due",
        "egr_raw_company_data",
        ["next_retry_at"],
        postgresql_where=sa.text("last_error IS NOT NULL AND processed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_egr_raw_retry_due", table_name="egr_raw_company_data")
    op.drop_column("egr_raw_company_data", "next_retry_at")
    op.drop_column("egr_raw_company_data", "error_attempts")
