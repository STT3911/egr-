"""Add per-endpoint columns to egr_raw_company_data

Revision ID: e5f6g7h8i9
Revises: b2c3d4e5f6g7
Create Date: 2026-01-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'e5f6g7h8i9'
down_revision = 'b2c3d4e5f6g7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('egr_raw_company_data', sa.Column('base_info', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('egr_raw_company_data', sa.Column('base_info_fetched_at', sa.DateTime(), nullable=True))
    op.add_column('egr_raw_company_data', sa.Column('addresses', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('egr_raw_company_data', sa.Column('addresses_fetched_at', sa.DateTime(), nullable=True))
    op.add_column('egr_raw_company_data', sa.Column('ved', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('egr_raw_company_data', sa.Column('ved_fetched_at', sa.DateTime(), nullable=True))
    op.add_column('egr_raw_company_data', sa.Column('names', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('egr_raw_company_data', sa.Column('names_fetched_at', sa.DateTime(), nullable=True))

    # Backfill from data
    op.execute("""
        UPDATE egr_raw_company_data
        SET
            base_info = data->'base_info',
            addresses = data->'addresses',
            ved = data->'ved',
            names = data->'names'
        WHERE data IS NOT NULL
    """)

    # Make data nullable (for new rows we can fill from columns)
    op.alter_column(
        'egr_raw_company_data',
        'data',
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'egr_raw_company_data',
        'data',
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
    )
    op.drop_column('egr_raw_company_data', 'names_fetched_at')
    op.drop_column('egr_raw_company_data', 'names')
    op.drop_column('egr_raw_company_data', 'ved_fetched_at')
    op.drop_column('egr_raw_company_data', 'ved')
    op.drop_column('egr_raw_company_data', 'addresses_fetched_at')
    op.drop_column('egr_raw_company_data', 'addresses')
    op.drop_column('egr_raw_company_data', 'base_info_fetched_at')
    op.drop_column('egr_raw_company_data', 'base_info')
