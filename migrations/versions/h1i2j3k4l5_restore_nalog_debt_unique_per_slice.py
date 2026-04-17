"""Restore nalog_debt_records uniqueness per inspectorate and slice.

Revision ID: h1i2j3k4l5
Revises: 6d5f919ecf17
Create Date: 2026-04-17 13:10:00.000000

"""
from alembic import op


revision = "h1i2j3k4l5"
down_revision = "6d5f919ecf17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_nalog_debt_unp_debt_date",
        "nalog_debt_records",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_nalog_debt_unp_imns_dates_slice",
        "nalog_debt_records",
        ["debtor_unp", "imns_code", "debt_date", "repayment_date", "slice_date"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_nalog_debt_unp_imns_dates_slice",
        "nalog_debt_records",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_nalog_debt_unp_debt_date",
        "nalog_debt_records",
        ["debtor_unp", "debt_date"],
    )
