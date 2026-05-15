"""add trade registry records

Revision ID: m6n7o8p9q0
Revises: l5m6n7o8p9
Create Date: 2026-05-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "m6n7o8p9q0"
down_revision = "l5m6n7o8p9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "trade_registry_records",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("egr_companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("unp", sa.BigInteger(), nullable=False),
        sa.Column("legal_name", sa.Text(), nullable=True),
        sa.Column("legal_address", sa.Text(), nullable=True),
        sa.Column("object_type", sa.Text(), nullable=True),
        sa.Column("object_name", sa.Text(), nullable=True),
        sa.Column("internet_shop_domain", sa.Text(), nullable=True),
        sa.Column("trade_network_name", sa.Text(), nullable=True),
        sa.Column("object_region", sa.Text(), nullable=True),
        sa.Column("object_district", sa.Text(), nullable=True),
        sa.Column("object_locality", sa.Text(), nullable=True),
        sa.Column("object_street", sa.Text(), nullable=True),
        sa.Column("object_building", sa.Text(), nullable=True),
        sa.Column("object_office", sa.Text(), nullable=True),
        sa.Column("object_contacts", sa.Text(), nullable=True),
        sa.Column("format_type", sa.Text(), nullable=True),
        sa.Column("location_type", sa.Text(), nullable=True),
        sa.Column("assortment_type", sa.Text(), nullable=True),
        sa.Column("is_firm", sa.String(length=32), nullable=True),
        sa.Column("trade_object_type", sa.Text(), nullable=True),
        sa.Column("trade_area", sa.String(length=64), nullable=True),
        sa.Column("retail_trade", sa.String(length=32), nullable=True),
        sa.Column("wholesale_trade", sa.String(length=32), nullable=True),
        sa.Column("retail_without_object_form", sa.Text(), nullable=True),
        sa.Column("wholesale_without_object", sa.String(length=32), nullable=True),
        sa.Column("goods_classes", sa.Text(), nullable=True),
        sa.Column("goods_groups", sa.Text(), nullable=True),
        sa.Column("goods_subgroups", sa.Text(), nullable=True),
        sa.Column("catering_format_type", sa.Text(), nullable=True),
        sa.Column("seats_count", sa.Integer(), nullable=True),
        sa.Column("public_seats_count", sa.Integer(), nullable=True),
        sa.Column("shopping_center_specializations", sa.Text(), nullable=True),
        sa.Column("shopping_center_trade_objects_count", sa.Integer(), nullable=True),
        sa.Column("shopping_center_catering_objects_count", sa.Integer(), nullable=True),
        sa.Column("shopping_center_trade_area", sa.String(length=64), nullable=True),
        sa.Column("market_type", sa.Text(), nullable=True),
        sa.Column("market_specialization", sa.Text(), nullable=True),
        sa.Column("market_places_count", sa.Integer(), nullable=True),
        sa.Column("market_trade_objects_count", sa.Integer(), nullable=True),
        sa.Column("registration_number", sa.String(length=64), nullable=False),
        sa.Column("inclusion_date", sa.Date(), nullable=True),
        sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column("source_file", sa.Text(), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sync_hash", sa.String(length=64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("unp", "registration_number", name="uq_trade_registry_records_unp_registration_number"),
    )
    op.create_index("idx_trade_registry_records_company_id", "trade_registry_records", ["company_id"])
    op.create_index("idx_trade_registry_records_unp", "trade_registry_records", ["unp"])
    op.create_index("idx_trade_registry_records_registration_number", "trade_registry_records", ["registration_number"])
    op.create_index("idx_trade_registry_records_source_date", "trade_registry_records", ["source_date"])
    op.create_index("idx_trade_registry_records_last_seen_at", "trade_registry_records", ["last_seen_at"])


def downgrade():
    op.drop_index("idx_trade_registry_records_last_seen_at", table_name="trade_registry_records")
    op.drop_index("idx_trade_registry_records_source_date", table_name="trade_registry_records")
    op.drop_index("idx_trade_registry_records_registration_number", table_name="trade_registry_records")
    op.drop_index("idx_trade_registry_records_unp", table_name="trade_registry_records")
    op.drop_index("idx_trade_registry_records_company_id", table_name="trade_registry_records")
    op.drop_table("trade_registry_records")
