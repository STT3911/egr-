"""Add company_address_keys table

Нормализованный ключ текущего адреса компании (без квартиры/офиса) — для
группировки "компании по одному адресу" (один дом).

Revision ID: addr1keys01
Revises: cc1contacts01
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = 'addr1keys01'
down_revision = 'cc1contacts01'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'company_address_keys',
        sa.Column('company_id', UUID(as_uuid=True), nullable=False),
        sa.Column('unp', sa.BigInteger(), nullable=False),
        sa.Column('full_address', sa.Text(), nullable=True),
        sa.Column('address_key', sa.Text(), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['egr_companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('company_id'),
    )
    op.create_index('ix_company_address_keys_unp', 'company_address_keys', ['unp'])
    op.create_index('ix_company_address_keys_address_key', 'company_address_keys', ['address_key'])


def downgrade() -> None:
    op.drop_index('ix_company_address_keys_address_key', table_name='company_address_keys')
    op.drop_index('ix_company_address_keys_unp', table_name='company_address_keys')
    op.drop_table('company_address_keys')
