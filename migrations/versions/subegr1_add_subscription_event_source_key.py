"""Add deterministic source keys for subscription events.

Revision ID: subegr1
Revises: minsklead1
Create Date: 2026-08-11
"""

from alembic import op
import sqlalchemy as sa


revision = "subegr1"
down_revision = "minsklead1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscription_events",
        sa.Column("source_key", sa.String(length=160), nullable=True),
    )
    op.create_unique_constraint(
        "uq_subscription_events_user_source_key",
        "subscription_events",
        ["user_id", "source_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_subscription_events_user_source_key",
        "subscription_events",
        type_="unique",
    )
    op.drop_column("subscription_events", "source_key")
