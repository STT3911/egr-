"""Add Bitrix24 app settings table

Revision ID: bitrix001
Revises: 
Create Date: 2026-03-30
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bitrix001'
down_revision = 'd4e5f6g7h8i9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'bitrix_app_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bitrix_domain', sa.String(length=255), nullable=True),
        sa.Column('bitrix_member_id', sa.String(length=100), nullable=True),
        sa.Column('access_token', sa.String(length=512), nullable=True),
        sa.Column('refresh_token', sa.String(length=512), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(), nullable=True),
        sa.Column('requisite_preset_id', sa.Integer(), nullable=True),
        sa.Column('requisite_preset_name', sa.String(length=255), nullable=True),
        sa.Column('unp_field_code', sa.String(length=100), nullable=True),
        sa.Column('unp_field_label', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bitrix_app_settings_id'), 'bitrix_app_settings', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_bitrix_app_settings_id'), table_name='bitrix_app_settings')
    op.drop_table('bitrix_app_settings')
