"""split subscription_events payload into old_value/new_value, add processed flag

Revision ID: a0b1c2d3e4
Revises: z9a0b1c2d3
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a0b1c2d3e4"
down_revision = "z9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # старый частичный индекс был по processed_at IS NULL — убираем
    op.drop_index("ix_subscription_events_unprocessed", table_name="subscription_events")

    op.add_column("subscription_events", sa.Column("old_value", sa.Text(), nullable=True))
    op.add_column("subscription_events", sa.Column("new_value", sa.Text(), nullable=True))
    op.add_column(
        "subscription_events",
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.drop_column("subscription_events", "payload")
    op.drop_column("subscription_events", "processed_at")

    op.create_index("ix_subscription_events_processed", "subscription_events", ["processed"])
    # частичный индекс под пулинг ещё-необработанных событий
    op.create_index(
        "ix_subscription_events_unprocessed",
        "subscription_events",
        ["id"],
        postgresql_where=sa.text("processed = false"),
    )


def downgrade() -> None:
    op.drop_index("ix_subscription_events_unprocessed", table_name="subscription_events")
    op.drop_index("ix_subscription_events_processed", table_name="subscription_events")

    op.add_column("subscription_events", sa.Column("payload", postgresql.JSONB(), nullable=True))
    op.add_column("subscription_events", sa.Column("processed_at", sa.DateTime(), nullable=True))

    op.drop_column("subscription_events", "processed")
    op.drop_column("subscription_events", "new_value")
    op.drop_column("subscription_events", "old_value")

    op.create_index(
        "ix_subscription_events_unprocessed",
        "subscription_events",
        ["id"],
        postgresql_where=sa.text("processed_at IS NULL"),
    )
