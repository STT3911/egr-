"""Add aggregated company_contacts table

Единое место под контакты компании из всех источников (ЕГР/МАРТ/ГИАС/ПВТ + ручные)
с дедупом и индексами под быструю выдачу и обратный поиск.

Revision ID: cc1contacts01
Revises: geo1coords01
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = 'cc1contacts01'
down_revision = 'geo1coords01'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'company_contacts',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('company_id', UUID(as_uuid=True), nullable=False),
        sa.Column('unp', sa.BigInteger(), nullable=True),
        sa.Column('contact_type', sa.String(length=16), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('value_norm', sa.Text(), nullable=False),
        sa.Column('full_name', sa.Text(), nullable=True),
        sa.Column('position', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('raw', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['egr_companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'contact_type', 'value_norm', 'source', name='uq_company_contact'),
    )
    op.create_index('ix_company_contacts_company_id', 'company_contacts', ['company_id'])
    op.create_index('ix_company_contacts_unp', 'company_contacts', ['unp'])
    op.create_index('ix_company_contacts_value_norm', 'company_contacts', ['value_norm'])


def downgrade() -> None:
    op.drop_index('ix_company_contacts_value_norm', table_name='company_contacts')
    op.drop_index('ix_company_contacts_unp', table_name='company_contacts')
    op.drop_index('ix_company_contacts_company_id', table_name='company_contacts')
    op.drop_table('company_contacts')
