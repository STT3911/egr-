"""add eaeu sez resident records

Revision ID: u4v5w6x7y8
Revises: t3u4v5w6x7
Create Date: 2026-05-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "u4v5w6x7y8"
down_revision = "t3u4v5w6x7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "eaeu_sez_resident_records",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("egr_companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("unp", sa.BigInteger(), nullable=False),
        sa.Column("country", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("short_name", sa.Text(), nullable=True),
        sa.Column("legal_address", sa.Text(), nullable=True),
        sa.Column("firm_name", sa.Text(), nullable=True),
        sa.Column("registration_agency", sa.Text(), nullable=True),
        sa.Column("sez_name", sa.Text(), nullable=True),
        sa.Column("project_name", sa.Text(), nullable=True),
        sa.Column("registry_entry_date", sa.Text(), nullable=True),
        sa.Column("certificate", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("item_id", name="uq_eaeu_sez_resident_records_item_id"),
    )
    op.create_index("idx_eaeu_sez_resident_records_item_id", "eaeu_sez_resident_records", ["item_id"])
    op.create_index("idx_eaeu_sez_resident_records_company_id", "eaeu_sez_resident_records", ["company_id"])
    op.create_index("idx_eaeu_sez_resident_records_unp", "eaeu_sez_resident_records", ["unp"])
    op.create_index("idx_eaeu_sez_resident_records_country", "eaeu_sez_resident_records", ["country"])
    op.create_index("idx_eaeu_sez_resident_records_last_seen_at", "eaeu_sez_resident_records", ["last_seen_at"])


def downgrade():
    op.drop_index("idx_eaeu_sez_resident_records_last_seen_at", table_name="eaeu_sez_resident_records")
    op.drop_index("idx_eaeu_sez_resident_records_country", table_name="eaeu_sez_resident_records")
    op.drop_index("idx_eaeu_sez_resident_records_unp", table_name="eaeu_sez_resident_records")
    op.drop_index("idx_eaeu_sez_resident_records_company_id", table_name="eaeu_sez_resident_records")
    op.drop_index("idx_eaeu_sez_resident_records_item_id", table_name="eaeu_sez_resident_records")
    op.drop_table("eaeu_sez_resident_records")
