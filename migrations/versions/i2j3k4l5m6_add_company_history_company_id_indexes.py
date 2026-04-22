"""Add company_id indexes for company history tables.

Revision ID: i2j3k4l5m6
Revises: h1i2j3k4l5
Create Date: 2026-04-22 16:15:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "i2j3k4l5m6"
down_revision = "h1i2j3k4l5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_egr_company_names_history_company_id",
        "egr_company_names_history",
        ["company_id"],
    )
    op.create_index(
        "ix_egr_company_addresses_history_company_id",
        "egr_company_addresses_history",
        ["company_id"],
    )
    op.create_index(
        "ix_egr_company_ved_history_company_id",
        "egr_company_ved_history",
        ["company_id"],
    )
    op.create_index(
        "ix_egr_company_contacts_history_company_id",
        "egr_company_contacts_history",
        ["company_id"],
    )
    op.create_index(
        "ix_egr_sync_history_company_id",
        "egr_sync_history",
        ["company_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_egr_sync_history_company_id", table_name="egr_sync_history")
    op.drop_index("ix_egr_company_contacts_history_company_id", table_name="egr_company_contacts_history")
    op.drop_index("ix_egr_company_ved_history_company_id", table_name="egr_company_ved_history")
    op.drop_index("ix_egr_company_addresses_history_company_id", table_name="egr_company_addresses_history")
    op.drop_index("ix_egr_company_names_history_company_id", table_name="egr_company_names_history")
