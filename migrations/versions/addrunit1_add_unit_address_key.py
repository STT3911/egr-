"""Add exact unit address key for address risk scoring.

Revision ID: addrunit1
Revises: subegr1
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa


revision = "addrunit1"
down_revision = "subegr1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_address_keys",
        sa.Column("unit_address_key", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_company_address_keys_unit_address_key",
        "company_address_keys",
        ["unit_address_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_address_keys_unit_address_key",
        table_name="company_address_keys",
    )
    op.drop_column("company_address_keys", "unit_address_key")
