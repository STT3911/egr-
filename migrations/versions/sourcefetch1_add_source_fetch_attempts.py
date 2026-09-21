"""Persist source retry state without altering business data."""
from alembic import op
import sqlalchemy as sa

revision = "sourcefetch1"
down_revision = "court1schema"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_fetch_attempts",
        sa.Column("source", sa.String(32), primary_key=True),
        sa.Column("unp", sa.BigInteger(), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.Column("next_check_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_source_fetch_attempts_due", "source_fetch_attempts",
                    ["source", "next_check_at", "unp"])


def downgrade():
    op.drop_index("ix_source_fetch_attempts_due", table_name="source_fetch_attempts")
    op.drop_table("source_fetch_attempts")
