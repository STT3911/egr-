"""Central UNP registry: egr_companies.source + gov_organizations.company_id

Делает egr_companies единым реестром всех УНП (ЕГР + найденные через ГРП).
- egr_companies.source: 'egr' (по умолчанию) | 'grp' — происхождение записи.
- gov_organizations.company_id: FK на egr_companies (классификатор ссылается на центр).

Revision ID: gov2cent01
Revises: gov1org01
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = 'gov2cent01'
down_revision = 'gov1org01'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Происхождение записи в центральном реестре.
    op.add_column(
        'egr_companies',
        sa.Column('source', sa.String(length=8), nullable=False, server_default='egr'),
    )
    op.create_index('ix_egr_companies_source', 'egr_companies', ['source'])

    # gov_organizations ссылается на центральный реестр.
    op.add_column(
        'gov_organizations',
        sa.Column('company_id', UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_gov_organizations_company_id', 'gov_organizations', 'egr_companies',
        ['company_id'], ['id'], ondelete='CASCADE',
    )
    op.create_index('ix_gov_organizations_company_id', 'gov_organizations', ['company_id'])


def downgrade() -> None:
    op.drop_index('ix_gov_organizations_company_id', table_name='gov_organizations')
    op.drop_constraint('fk_gov_organizations_company_id', 'gov_organizations', type_='foreignkey')
    op.drop_column('gov_organizations', 'company_id')
    op.drop_index('ix_egr_companies_source', table_name='egr_companies')
    op.drop_column('egr_companies', 'source')
