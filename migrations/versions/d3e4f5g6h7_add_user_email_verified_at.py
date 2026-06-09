"""add users.email_verified_at (dormant, under future email verification)

Revision ID: d3e4f5g6h7
Revises: c2d3e4f5g6
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa


revision = "d3e4f5g6h7"
down_revision = "c2d3e4f5g6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")
