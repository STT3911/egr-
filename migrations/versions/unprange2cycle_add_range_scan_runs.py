"""Add persistent UNP range scan cycles.

Revision ID: unprange2cycle
Revises: soato1bigint
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa


revision = "unprange2cycle"
down_revision = "soato1bigint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "unp_range_scan_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("cycle_number", sa.BigInteger(), nullable=False),
        sa.Column("source_range_id", sa.BigInteger(), nullable=True),
        sa.Column("region", sa.SmallInteger(), nullable=False),
        sa.Column("source_seq_start", sa.Integer(), nullable=False),
        sa.Column("source_seq_end", sa.Integer(), nullable=False),
        sa.Column("scan_start", sa.Integer(), nullable=False),
        sa.Column("scan_end", sa.Integer(), nullable=False),
        sa.Column("next_sequence", sa.Integer(), nullable=False),
        sa.Column("first_checked_unp", sa.BigInteger(), nullable=True),
        sa.Column("last_checked_unp", sa.BigInteger(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "checked_count",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "found_count",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "not_found_count",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "error_count",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "region BETWEEN 1 AND 9",
            name="ck_unp_range_scan_region",
        ),
        sa.CheckConstraint(
            "scan_start BETWEEN 0 AND 9999999 "
            "AND scan_end BETWEEN scan_start AND 9999999",
            name="ck_unp_range_scan_sequence",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'error')",
            name="ck_unp_range_scan_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cycle_number",
            "region",
            "source_seq_start",
            "source_seq_end",
            name="uq_unp_range_scan_cycle_range",
        ),
    )
    op.create_index(
        "ix_unp_range_scan_cycle_status",
        "unp_range_scan_runs",
        ["cycle_number", "status", "region", "scan_start"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_unp_range_scan_cycle_status",
        table_name="unp_range_scan_runs",
    )
    op.drop_table("unp_range_scan_runs")
