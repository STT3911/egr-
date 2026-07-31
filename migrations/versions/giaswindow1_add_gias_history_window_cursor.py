"""Add a durable time-window cursor for the GIAS contract backfill.

Revision ID: giaswindow1
Revises: subread1
"""

from alembic import op
import sqlalchemy as sa


revision = "giaswindow1"
down_revision = "subread1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gias_contract_sync_state",
        sa.Column("history_window_start_ms", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "gias_contract_sync_state",
        sa.Column("history_window_end_ms", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "gias_contract_sync_state",
        sa.Column("history_target_ms", sa.BigInteger(), nullable=True),
    )
    op.execute(
        """
        UPDATE gias_contract_sync_state
        SET initial_complete = false,
            next_page = 0,
            total_pages = NULL,
            history_window_start_ms = NULL,
            history_window_end_ms = NULL,
            history_target_ms = NULL
        """
    )


def downgrade() -> None:
    op.drop_column("gias_contract_sync_state", "history_target_ms")
    op.drop_column("gias_contract_sync_state", "history_window_end_ms")
    op.drop_column("gias_contract_sync_state", "history_window_start_ms")
