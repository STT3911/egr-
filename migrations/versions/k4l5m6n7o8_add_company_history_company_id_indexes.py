"""Add company_id indexes for company history tables.

Revision ID: k4l5m6n7o8
Revises: j3k4l5m6n7
Create Date: 2026-04-22 16:15:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "k4l5m6n7o8"
down_revision = "j3k4l5m6n7"
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
