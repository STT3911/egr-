"""Add dated public leadership observations.

Revision ID: minsklead1
Revises: giasacct1
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "minsklead1"
down_revision = "giasacct1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_leadership_observations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("unp", sa.BigInteger(), nullable=True),
        sa.Column("person_name", sa.Text(), nullable=False),
        sa.Column("position", sa.Text(), nullable=False),
        sa.Column("organization_name", sa.Text(), nullable=False),
        sa.Column("organization_name_norm", sa.Text(), nullable=True),
        sa.Column("is_head", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("exam_type", sa.String(length=32), nullable=True),
        sa.Column("source_name", sa.String(length=64), nullable=False),
        sa.Column("source_title", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_row_no", sa.Integer(), nullable=True),
        sa.Column("match_method", sa.String(length=32), nullable=True),
        sa.Column("match_confidence", sa.Float(), nullable=True),
        sa.Column(
            "raw_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("sync_key", sa.String(length=64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["egr_companies.id"],
            name="fk_company_leadership_observations_company",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("sync_key", name="uq_company_leadership_observations_sync_key"),
    )

    for name, columns in (
        ("idx_company_leadership_company", ["company_id"]),
        ("idx_company_leadership_unp", ["unp"]),
        ("idx_company_leadership_person", ["person_name"]),
        ("idx_company_leadership_org_norm", ["organization_name_norm"]),
        ("idx_company_leadership_is_head", ["is_head"]),
        ("idx_company_leadership_event_date", ["event_date"]),
        ("idx_company_leadership_last_seen", ["last_seen_at"]),
    ):
        op.create_index(name, "company_leadership_observations", columns)


def downgrade() -> None:
    op.drop_table("company_leadership_observations")
