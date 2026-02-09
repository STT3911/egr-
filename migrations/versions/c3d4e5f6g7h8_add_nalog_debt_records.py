"""Add nalog_debt_records table (portal.nalog.gov.by debt data)

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-01-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c3d4e5f6g7h8"
down_revision = "b2c3d4e5f6g7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nalog_debt_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("debtor_unp", sa.BigInteger(), nullable=False),
        sa.Column("imns_code", sa.String(10), nullable=False),
        sa.Column("imns_name", sa.String(500), nullable=True),
        sa.Column("debt_date", sa.String(50), nullable=False),
        sa.Column("repayment_date", sa.String(50), nullable=False),
        sa.Column("slice_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "debtor_unp",
            "imns_code",
            "debt_date",
            "repayment_date",
            "slice_date",
            name="uq_nalog_debt_unp_imns_dates_slice",
        ),
    )
    op.create_index("ix_nalog_debt_records_debtor_unp", "nalog_debt_records", ["debtor_unp"])
    op.create_index("ix_nalog_debt_records_slice_date", "nalog_debt_records", ["slice_date"])
    op.create_index(
        "ix_nalog_debt_records_unp_slice",
        "nalog_debt_records",
        ["debtor_unp", "slice_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_nalog_debt_records_unp_slice", "nalog_debt_records")
    op.drop_index("ix_nalog_debt_records_slice_date", "nalog_debt_records")
    op.drop_index("ix_nalog_debt_records_debtor_unp", "nalog_debt_records")
    op.drop_table("nalog_debt_records")
