"""Update unique constraint for nalog_debt_records

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-01-22

"""
from alembic import op


revision = "d4e5f6g7h8i9"
down_revision = "c3d4e5f6g7h8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old unique constraint (by UNP + IMNS + dates + slice)
    op.drop_constraint(
        "uq_nalog_debt_unp_imns_dates_slice",
        "nalog_debt_records",
        type_="unique",
    )

    # Add new unique constraint: one record per UNP + debt_date
    op.create_unique_constraint(
        "uq_nalog_debt_unp_debt_date",
        "nalog_debt_records",
        ["debtor_unp", "debt_date"],
    )


def downgrade() -> None:
    # Revert to old unique constraint definition
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

