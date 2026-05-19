"""add pvt resident records

Revision ID: o8p9q0r1s2
Revises: n7o8p9q0r1
Create Date: 2026-05-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "o8p9q0r1s2"
down_revision = "n7o8p9q0r1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pvt_resident_records",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("egr_companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("unp", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("profile_url", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("unp", name="uq_pvt_resident_records_unp"),
    )
    op.create_index("idx_pvt_resident_records_company_id", "pvt_resident_records", ["company_id"])
    op.create_index("idx_pvt_resident_records_unp", "pvt_resident_records", ["unp"])
    op.create_index("idx_pvt_resident_records_last_seen_at", "pvt_resident_records", ["last_seen_at"])


def downgrade():
    op.drop_index("idx_pvt_resident_records_last_seen_at", table_name="pvt_resident_records")
    op.drop_index("idx_pvt_resident_records_unp", table_name="pvt_resident_records")
    op.drop_index("idx_pvt_resident_records_company_id", table_name="pvt_resident_records")
    op.drop_table("pvt_resident_records")
