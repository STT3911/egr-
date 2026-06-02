"""add belltpp own certificates

Revision ID: x7y8z9a0b1
Revises: w6x7y8z9a0
Create Date: 2026-06-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "x7y8z9a0b1"
down_revision = "w6x7y8z9a0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "belltpp_own_certificates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("egr_companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("holder_unp", sa.BigInteger(), nullable=False),
        sa.Column("holder_name", sa.Text(), nullable=False),
        sa.Column("cert_number", sa.String(length=64), nullable=False),
        sa.Column("blank_number", sa.String(length=64), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("verify_url", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_page", sa.Integer(), nullable=False),
        sa.Column("source_position", sa.Integer(), nullable=True),
        sa.Column("source_id", sa.BigInteger(), nullable=True),
        sa.Column("products", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sync_key", sa.String(length=64), nullable=False),
        sa.Column("sync_hash", sa.String(length=64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("sync_key", name="uq_belltpp_own_certificates_sync_key"),
    )
    op.create_index("idx_belltpp_own_certificates_company_id", "belltpp_own_certificates", ["company_id"])
    op.create_index("idx_belltpp_own_certificates_holder_unp", "belltpp_own_certificates", ["holder_unp"])
    op.create_index("idx_belltpp_own_certificates_cert_number", "belltpp_own_certificates", ["cert_number"])
    op.create_index("idx_belltpp_own_certificates_blank_number", "belltpp_own_certificates", ["blank_number"])
    op.create_index("idx_belltpp_own_certificates_issue_date", "belltpp_own_certificates", ["issue_date"])
    op.create_index("idx_belltpp_own_certificates_valid_until", "belltpp_own_certificates", ["valid_until"])
    op.create_index("idx_belltpp_own_certificates_source_id", "belltpp_own_certificates", ["source_id"])
    op.create_index("idx_belltpp_own_certificates_last_seen_at", "belltpp_own_certificates", ["last_seen_at"])


def downgrade():
    op.drop_index("idx_belltpp_own_certificates_last_seen_at", table_name="belltpp_own_certificates")
    op.drop_index("idx_belltpp_own_certificates_source_id", table_name="belltpp_own_certificates")
    op.drop_index("idx_belltpp_own_certificates_valid_until", table_name="belltpp_own_certificates")
    op.drop_index("idx_belltpp_own_certificates_issue_date", table_name="belltpp_own_certificates")
    op.drop_index("idx_belltpp_own_certificates_blank_number", table_name="belltpp_own_certificates")
    op.drop_index("idx_belltpp_own_certificates_cert_number", table_name="belltpp_own_certificates")
    op.drop_index("idx_belltpp_own_certificates_holder_unp", table_name="belltpp_own_certificates")
    op.drop_index("idx_belltpp_own_certificates_company_id", table_name="belltpp_own_certificates")
    op.drop_table("belltpp_own_certificates")
