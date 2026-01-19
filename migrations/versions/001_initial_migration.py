"""Initial migration for EGR tables

Revision ID: 001_egr_initial
Revises: 
Create Date: 2024-12-24 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001_egr_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # System State
    op.create_table('egr_system_state',
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.String(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('key')
    )
    
    # Raw Data
    op.create_table('egr_raw_company_data',
        sa.Column('unp', sa.BigInteger(), nullable=False),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('unp')
    )
    op.create_index('idx_egr_raw_company_data_unp', 'egr_raw_company_data', ['unp'], unique=True)
    
    # Companies
    op.create_table('egr_companies',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('unp', sa.BigInteger(), nullable=False),
        sa.Column('current_status_code', sa.Integer(), nullable=True),
        sa.Column('registration_date', sa.Date(), nullable=True),
        sa.Column('liquidation_date', sa.Date(), nullable=True),
        sa.Column('liquidation_reason_id', sa.Integer(), nullable=True),
        sa.Column('liquidation_decision_no', sa.String(), nullable=True),
        sa.Column('liquidation_authority_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_egr_companies_unp', 'egr_companies', ['unp'], unique=True)
    
    # History Tables
    op.create_table('egr_company_names_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('full_name_ru', sa.String(), nullable=True),
        sa.Column('short_name_ru', sa.String(), nullable=True),
        sa.Column('full_name_by', sa.String(), nullable=True),
        sa.Column('valid_from', sa.Date(), nullable=True),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['egr_companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('egr_company_addresses_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('full_address', sa.Text(), nullable=True),
        sa.Column('postal_code', sa.Integer(), nullable=True),
        sa.Column('region', sa.String(), nullable=True),
        sa.Column('district', sa.String(), nullable=True),
        sa.Column('valid_from', sa.Date(), nullable=True),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['egr_companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('egr_company_ved_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ved_code', sa.String(), nullable=True),
        sa.Column('ved_name', sa.String(), nullable=True),
        sa.Column('valid_from', sa.Date(), nullable=True),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['egr_companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('egr_company_contacts_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('website', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('fax', sa.String(), nullable=True),
        sa.Column('valid_from', sa.Date(), nullable=True),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['egr_companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Sync History
    op.create_table('egr_sync_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sync_type', sa.String(length=50), nullable=False),
        sa.Column('sync_date', sa.DateTime(), nullable=False),
        sa.Column('changes_detected', sa.Boolean(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['egr_companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # API Logs
    op.create_table('egr_api_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('request_id', sa.String(length=100), nullable=False),
        sa.Column('company_unp', sa.BigInteger(), nullable=True),
        sa.Column('endpoint', sa.String(length=200), nullable=False),
        sa.Column('method', sa.String(length=10), nullable=False),
        sa.Column('response_status', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('egr_api_logs')
    op.drop_table('egr_sync_history')
    op.drop_table('egr_company_contacts_history')
    op.drop_table('egr_company_ved_history')
    op.drop_table('egr_company_addresses_history')
    op.drop_table('egr_company_names_history')
    op.drop_table('egr_companies')
    op.drop_table('egr_raw_company_data')
    op.drop_table('egr_system_state')






