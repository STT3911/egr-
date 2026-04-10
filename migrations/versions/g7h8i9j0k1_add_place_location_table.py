"""Add company placeLocation table

Revision ID: g7h8i9j0k1
Revises: f6g7h8i9j0
Create Date: 2026-04-10 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "g7h8i9j0k1"
down_revision = "f6g7h8i9j0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "egr_company_place_locations",
        sa.Column("unp", sa.BigInteger(), primary_key=True),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_egr_company_place_locations_unp", "egr_company_place_locations", ["unp"])
    op.create_index("idx_egr_company_place_locations_fetched_at", "egr_company_place_locations", ["fetched_at"])


def downgrade() -> None:
    op.drop_index("idx_egr_company_place_locations_fetched_at", table_name="egr_company_place_locations")
    op.drop_index("idx_egr_company_place_locations_unp", table_name="egr_company_place_locations")
    op.drop_table("egr_company_place_locations")

