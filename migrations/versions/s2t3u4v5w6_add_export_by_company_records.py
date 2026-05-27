"""add export.by company records

Revision ID: s2t3u4v5w6
Revises: r1s2t3u4v5
Create Date: 2026-05-27 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "s2t3u4v5w6"
down_revision = "r1s2t3u4v5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "export_by_company_records",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("export_by_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("egr_companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("unp", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=True),
        sa.Column("logo", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("country", sa.String(length=255), nullable=True),
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("match_status", sa.String(length=32), nullable=False, server_default=sa.text("'not_found'")),
        sa.Column("match_method", sa.String(length=32), nullable=True),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("matched_name", sa.Text(), nullable=True),
        sa.Column(
            "candidate_unps",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("export_by_id", name="uq_export_by_company_records_export_by_id"),
    )
    op.create_index("idx_export_by_company_records_company_id", "export_by_company_records", ["company_id"])
    op.create_index("idx_export_by_company_records_unp", "export_by_company_records", ["unp"])
    op.create_index("idx_export_by_company_records_export_by_id", "export_by_company_records", ["export_by_id"])
    op.create_index("idx_export_by_company_records_normalized_name", "export_by_company_records", ["normalized_name"])
    op.create_index("idx_export_by_company_records_match_status", "export_by_company_records", ["match_status"])
    op.create_index("idx_export_by_company_records_last_seen_at", "export_by_company_records", ["last_seen_at"])


def downgrade():
    op.drop_index("idx_export_by_company_records_last_seen_at", table_name="export_by_company_records")
    op.drop_index("idx_export_by_company_records_match_status", table_name="export_by_company_records")
    op.drop_index("idx_export_by_company_records_normalized_name", table_name="export_by_company_records")
    op.drop_index("idx_export_by_company_records_export_by_id", table_name="export_by_company_records")
    op.drop_index("idx_export_by_company_records_unp", table_name="export_by_company_records")
    op.drop_index("idx_export_by_company_records_company_id", table_name="export_by_company_records")
    op.drop_table("export_by_company_records")
