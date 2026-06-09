"""add users, company_subscriptions, subscription_events

Подписки пользователей на события компаний + очередь сработавших событий.

Revision ID: z9a0b1c2d3
Revises: y8z9a0b1c2
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "z9a0b1c2d3"
down_revision = "y8z9a0b1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- users --------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    # --- company_subscriptions ---------------------------------------------
    op.create_table(
        "company_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("unp", sa.BigInteger(), nullable=False),
        sa.Column("event_types", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="web"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "unp", name="uq_company_subscriptions_user_unp"),
    )
    op.create_index("ix_company_subscriptions_user_id", "company_subscriptions", ["user_id"])
    op.create_index("ix_company_subscriptions_unp", "company_subscriptions", ["unp"])

    # --- subscription_events (очередь) -------------------------------------
    op.create_table(
        "subscription_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("unp", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_subscription_events_user_id", "subscription_events", ["user_id"])
    op.create_index("ix_subscription_events_unp", "subscription_events", ["unp"])
    op.create_index("ix_subscription_events_event_type", "subscription_events", ["event_type"])
    # частичный индекс под пулинг необработанных событий
    op.create_index("ix_subscription_events_unprocessed", "subscription_events",
                    ["id"], postgresql_where=sa.text("processed_at IS NULL"))


def downgrade() -> None:
    op.drop_table("subscription_events")
    op.drop_table("company_subscriptions")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
