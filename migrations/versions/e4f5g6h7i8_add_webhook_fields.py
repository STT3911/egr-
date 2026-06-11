"""add webhook fields (users.webhook_url/secret, subscription_events delivery cols)

Revision ID: e4f5g6h7i8
Revises: d3e4f5g6h7
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa


revision = "e4f5g6h7i8"
down_revision = "d3e4f5g6h7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("webhook_url", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("webhook_secret", sa.String(length=64), nullable=True))

    op.add_column(
        "subscription_events",
        sa.Column("delivery_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("subscription_events", sa.Column("last_delivery_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("subscription_events", "last_delivery_error")
    op.drop_column("subscription_events", "delivery_attempts")
    op.drop_column("users", "webhook_secret")
    op.drop_column("users", "webhook_url")
