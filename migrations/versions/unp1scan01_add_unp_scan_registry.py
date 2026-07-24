"""Add UNP scan candidates and issuance ranges.

Revision ID: unp1scan01
Revises: search2reverse
"""

from alembic import op
import sqlalchemy as sa


revision = "unp1scan01"
down_revision = "search2reverse"
branch_labels = None
depends_on = None


SOURCE_STATUSES = "'pending', 'found', 'not_found', 'error'"
OVERALL_STATUSES = "'pending', 'found', 'not_found', 'partial', 'error'"


def upgrade() -> None:
    op.create_table(
        "unp_scan_candidates",
        sa.Column("unp", sa.BigInteger(), nullable=False),
        sa.Column("region", sa.SmallInteger(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "checksum_valid",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "known_in_db",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "egr_status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "grp_status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "overall_status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("first_checked_at", sa.DateTime(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("next_check_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
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
        sa.CheckConstraint("region BETWEEN 1 AND 9", name="ck_unp_scan_region"),
        sa.CheckConstraint(
            "sequence BETWEEN 0 AND 9999999",
            name="ck_unp_scan_sequence",
        ),
        sa.CheckConstraint(
            f"egr_status IN ({SOURCE_STATUSES})",
            name="ck_unp_scan_egr_status",
        ),
        sa.CheckConstraint(
            f"grp_status IN ({SOURCE_STATUSES})",
            name="ck_unp_scan_grp_status",
        ),
        sa.CheckConstraint(
            f"overall_status IN ({OVERALL_STATUSES})",
            name="ck_unp_scan_overall_status",
        ),
        sa.PrimaryKeyConstraint("unp"),
        sa.UniqueConstraint(
            "region",
            "sequence",
            name="uq_unp_scan_region_sequence",
        ),
    )
    op.create_index(
        "ix_unp_scan_candidates_status",
        "unp_scan_candidates",
        ["overall_status", "region", "sequence"],
    )
    op.create_index(
        "ix_unp_scan_candidates_last_checked",
        "unp_scan_candidates",
        ["last_checked_at"],
    )

    op.create_table(
        "unp_issuance_ranges",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("region", sa.SmallInteger(), nullable=False),
        sa.Column("seq_start", sa.Integer(), nullable=False),
        sa.Column("seq_end", sa.Integer(), nullable=False),
        sa.Column("first_unp", sa.BigInteger(), nullable=False),
        sa.Column("last_unp", sa.BigInteger(), nullable=False),
        sa.Column("known_count", sa.Integer(), nullable=False),
        sa.Column("gap_limit", sa.Integer(), nullable=False),
        sa.Column("scan_start", sa.Integer(), nullable=False),
        sa.Column("scan_end", sa.Integer(), nullable=False),
        sa.Column(
            "is_latest",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "refreshed_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "region BETWEEN 1 AND 9",
            name="ck_unp_range_region",
        ),
        sa.CheckConstraint(
            "seq_start BETWEEN 0 AND 9999999 AND seq_end BETWEEN seq_start AND 9999999",
            name="ck_unp_range_sequence",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "region",
            "seq_start",
            "seq_end",
            name="uq_unp_issuance_range",
        ),
    )
    op.create_index(
        "ix_unp_issuance_ranges_region_latest",
        "unp_issuance_ranges",
        ["region", "is_latest", "seq_end"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_unp_issuance_ranges_region_latest",
        table_name="unp_issuance_ranges",
    )
    op.drop_table("unp_issuance_ranges")
    op.drop_index(
        "ix_unp_scan_candidates_last_checked",
        table_name="unp_scan_candidates",
    )
    op.drop_index(
        "ix_unp_scan_candidates_status",
        table_name="unp_scan_candidates",
    )
    op.drop_table("unp_scan_candidates")
