"""Add lat/lon/geocoded_at to egr_company_place_locations

Координаты места нахождения компании. Геокодинг адреса выполняется через
OSM/Nominatim (лицензия разрешает хранение результатов), НЕ через Яндекс.

Revision ID: geo1coords01
Revises: gov2cent01
Create Date: 2026-06-24 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "geo1coords01"
down_revision = "gov2cent01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("egr_company_place_locations", sa.Column("lat", sa.Float(), nullable=True))
    op.add_column("egr_company_place_locations", sa.Column("lon", sa.Float(), nullable=True))
    op.add_column("egr_company_place_locations", sa.Column("geocoded_at", sa.DateTime(), nullable=True))
    # Частичный индекс: быстро находить адреса, ещё не превращённые в координаты.
    op.create_index(
        "idx_place_locations_need_geocode",
        "egr_company_place_locations",
        ["unp"],
        postgresql_where=sa.text("address IS NOT NULL AND lat IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_place_locations_need_geocode", table_name="egr_company_place_locations")
    op.drop_column("egr_company_place_locations", "geocoded_at")
    op.drop_column("egr_company_place_locations", "lon")
    op.drop_column("egr_company_place_locations", "lat")
