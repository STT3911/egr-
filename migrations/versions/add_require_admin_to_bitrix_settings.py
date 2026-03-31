"""Add require_admin column to bitrix_app_settings

Revision ID: add_require_admin
Revises: 
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'add_require_admin'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column(
        'bitrix_app_settings',
        sa.Column('require_admin', sa.Boolean(), nullable=False, server_default='false')
    )

def downgrade() -> None:
    op.drop_column('bitrix_app_settings', 'require_admin')
