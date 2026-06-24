"""Add gov_organizations directory

Самостоятельный справочник госорганизаций-юрлиц, наполняемый классификатором
поверх egr_raw_company_data + grp_taxpayer_data. Ключ — УНП, без FK к egr_companies.

Revision ID: gov1org01
Revises: bx3creds01
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = 'gov1org01'
down_revision = 'bx3creds01'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'gov_organizations',
        sa.Column('unp', sa.BigInteger(), nullable=False),
        sa.Column('full_name', sa.Text(), nullable=True),
        sa.Column('short_name', sa.Text(), nullable=True),
        sa.Column('opf_code', sa.Integer(), nullable=True),
        sa.Column('opf_name', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=32), nullable=False),
        sa.Column('ownership', sa.String(length=16), nullable=False),
        sa.Column('source', sa.String(length=8), nullable=False),
        sa.Column('matched_marker', sa.Text(), nullable=True),
        sa.Column('classified_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('unp'),
    )
    op.create_index('ix_gov_organizations_unp', 'gov_organizations', ['unp'])
    op.create_index('ix_gov_organizations_opf_code', 'gov_organizations', ['opf_code'])
    op.create_index('ix_gov_organizations_category', 'gov_organizations', ['category'])
    op.create_index('ix_gov_organizations_ownership', 'gov_organizations', ['ownership'])
    op.create_index('ix_gov_organizations_source', 'gov_organizations', ['source'])


def downgrade() -> None:
    op.drop_index('ix_gov_organizations_source', table_name='gov_organizations')
    op.drop_index('ix_gov_organizations_ownership', table_name='gov_organizations')
    op.drop_index('ix_gov_organizations_category', table_name='gov_organizations')
    op.drop_index('ix_gov_organizations_opf_code', table_name='gov_organizations')
    op.drop_index('ix_gov_organizations_unp', table_name='gov_organizations')
    op.drop_table('gov_organizations')
