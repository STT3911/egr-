"""add bankrot case datasets

Revision ID: bank1datasets
Revises: subq2chan01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "bank1datasets"
down_revision = "subq2chan01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bankrot_case_datasets",
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("dataset_type", sa.String(length=64), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("http_method", sa.String(length=8), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fetch_error", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["case_id"], ["bankrot_cases.case_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("case_id", "dataset_type"),
    )
    op.create_index(
        "idx_bankrot_case_datasets_type",
        "bankrot_case_datasets",
        ["dataset_type"],
    )
    op.create_index(
        "idx_bankrot_case_datasets_fetched_at",
        "bankrot_case_datasets",
        ["fetched_at"],
    )


def downgrade():
    op.drop_index(
        "idx_bankrot_case_datasets_fetched_at", table_name="bankrot_case_datasets"
    )
    op.drop_index(
        "idx_bankrot_case_datasets_type", table_name="bankrot_case_datasets"
    )
    op.drop_table("bankrot_case_datasets")
