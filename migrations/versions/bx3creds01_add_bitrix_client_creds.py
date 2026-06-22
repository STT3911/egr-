"""Add per-portal Bitrix OAuth client credentials

Хранение client_id/client_secret по каждому порталу (мультитенант для локальных
приложений), вместо единственной пары в .env.

Revision ID: bx3creds01
Revises: bx2masks01
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bx3creds01'
down_revision = 'bx2masks01'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bitrix_app_settings', sa.Column('bitrix_client_id', sa.String(length=255), nullable=True))
    op.add_column('bitrix_app_settings', sa.Column('bitrix_client_secret', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('bitrix_app_settings', 'bitrix_client_secret')
    op.drop_column('bitrix_app_settings', 'bitrix_client_id')
