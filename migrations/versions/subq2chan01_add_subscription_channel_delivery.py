"""per-channel delivery tracking for subscription_events (webhook + telegram)

Раньше доставка вебхука и телеграма делила один processed_at: доставив в один
канал, задача помечала событие обработанным, и во второй канал оно не уходило.
Добавляем независимые поля доставки на каждый канал.

Revision ID: subq2chan01
Revises: addr1keys01
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa


revision = "subq2chan01"
down_revision = "addr1keys01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscription_events", sa.Column("webhook_delivered_at", sa.DateTime(), nullable=True))
    op.add_column("subscription_events", sa.Column("webhook_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("subscription_events", sa.Column("webhook_error", sa.Text(), nullable=True))
    op.add_column("subscription_events", sa.Column("telegram_delivered_at", sa.DateTime(), nullable=True))
    op.add_column("subscription_events", sa.Column("telegram_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("subscription_events", sa.Column("telegram_error", sa.Text(), nullable=True))

    # Бэкфилл: уже доставленные события (processed_at не пуст) считаем доставленными
    # в оба канала, чтобы новая логика не разослала их повторно.
    op.execute(
        "UPDATE subscription_events "
        "SET webhook_delivered_at = processed_at, telegram_delivered_at = processed_at "
        "WHERE processed_at IS NOT NULL"
    )

    # Частичные индексы под выборку недоставленного по каждому каналу.
    op.create_index(
        "ix_sub_events_webhook_pending", "subscription_events", ["id"],
        postgresql_where=sa.text("webhook_delivered_at IS NULL"),
    )
    op.create_index(
        "ix_sub_events_telegram_pending", "subscription_events", ["id"],
        postgresql_where=sa.text("telegram_delivered_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_sub_events_telegram_pending", table_name="subscription_events")
    op.drop_index("ix_sub_events_webhook_pending", table_name="subscription_events")
    op.drop_column("subscription_events", "telegram_error")
    op.drop_column("subscription_events", "telegram_attempts")
    op.drop_column("subscription_events", "telegram_delivered_at")
    op.drop_column("subscription_events", "webhook_error")
    op.drop_column("subscription_events", "webhook_attempts")
    op.drop_column("subscription_events", "webhook_delivered_at")
