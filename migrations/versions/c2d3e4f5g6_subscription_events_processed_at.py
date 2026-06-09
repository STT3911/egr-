"""replace subscription_events.processed (bool) with processed_at (timestamp, nullable)

processed_at = NULL означает «ещё не обработано»; можно сбросить в NULL,
чтобы обработать заново. occurred_at — когда событие возникло.

Revision ID: c2d3e4f5g6
Revises: b1c2d3e4f5
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa


revision = "c2d3e4f5g6"
down_revision = "b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_subscription_events_unprocessed", table_name="subscription_events")
    op.drop_index("ix_subscription_events_processed", table_name="subscription_events")
    op.drop_column("subscription_events", "processed")

    op.add_column("subscription_events", sa.Column("processed_at", sa.DateTime(), nullable=True))
    op.create_index("ix_subscription_events_processed_at", "subscription_events", ["processed_at"])
    op.create_index(
        "ix_subscription_events_unprocessed",
        "subscription_events",
        ["id"],
        postgresql_where=sa.text("processed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_subscription_events_unprocessed", table_name="subscription_events")
    op.drop_index("ix_subscription_events_processed_at", table_name="subscription_events")
    op.drop_column("subscription_events", "processed_at")

    op.add_column(
        "subscription_events",
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_subscription_events_processed", "subscription_events", ["processed"])
    op.create_index(
        "ix_subscription_events_unprocessed",
        "subscription_events",
        ["id"],
        postgresql_where=sa.text("processed = false"),
    )
