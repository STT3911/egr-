"""Add web read state to subscription events.

Revision ID: subread1
Revises: unprange2cycle
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa


revision = "subread1"
down_revision = "unprange2cycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscription_events",
        sa.Column("read_at", sa.DateTime(), nullable=True),
    )
    op.execute(
        """
        UPDATE subscription_events
        SET read_at = processed_at
        WHERE processed_at IS NOT NULL
        """
    )
    op.create_index(
        "ix_subscription_events_read_at",
        "subscription_events",
        ["read_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_subscription_events_read_at",
        table_name="subscription_events",
    )
    op.drop_column("subscription_events", "read_at")
