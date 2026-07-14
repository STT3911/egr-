"""Add trigram index for reverse company address search.

Revision ID: search2reverse
Revises: bank1datasets
Create Date: 2026-07-14
"""
from alembic import op


revision = "search2reverse"
down_revision = "bank1datasets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_company_address_keys_address_key_trgm "
            "ON company_address_keys USING gin (address_key gin_trgm_ops)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_company_address_keys_address_key_trgm")
