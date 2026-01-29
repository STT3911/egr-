"""Add missing reference tables and events

Revision ID: b2c3d4e5f6g7
Revises: 80dada155a2c
Create Date: 2026-01-12 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6g7'
down_revision = '80dada155a2c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tables only if they don't exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()
    
    # 6. Справочник видов экономической деятельности - TSI00114
    if 'ref_ved' not in existing_tables:
        op.create_table(
            'ref_ved',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('code', sa.String()),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('system_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now())
        )
        op.create_index('idx_ref_ved_code', 'ref_ved', ['code'])
        op.create_index('idx_ref_ved_name', 'ref_ved', ['name'])
        op.execute("""
        CREATE TRIGGER update_ref_ved_updated_at BEFORE UPDATE ON ref_ved 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
    
    # 7. Справочник стран мира - TSI00201
    if 'ref_countries' not in existing_tables:
        op.create_table(
            'ref_countries',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('code', sa.Integer()),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('system_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now())
        )
        op.create_index('idx_ref_countries_name', 'ref_countries', ['name'])
        op.execute("""
        CREATE TRIGGER update_ref_countries_updated_at BEFORE UPDATE ON ref_countries 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
    
    # 8. Справочник СОАТО (территории РБ) - TSI00202
    if 'ref_soato' not in existing_tables:
        op.create_table(
            'ref_soato',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('code', sa.BigInteger()),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('object_number', sa.Integer()),
            sa.Column('system_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now())
        )
        op.create_index('idx_ref_soato_code', 'ref_soato', ['code'])
        op.create_index('idx_ref_soato_name', 'ref_soato', ['name'])
        op.execute("""
        CREATE TRIGGER update_ref_soato_updated_at BEFORE UPDATE ON ref_soato 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
    
    # 9. Справочник оснований для внесения - TSI00213
    if 'ref_foundations' not in existing_tables:
        op.create_table(
            'ref_foundations',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('code', sa.Integer()),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('system_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now())
        )
        op.create_index('idx_ref_foundations_name', 'ref_foundations', ['name'])
        op.execute("""
        CREATE TRIGGER update_ref_foundations_updated_at BEFORE UPDATE ON ref_foundations 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
    
    # 10. Справочник событий субъектов - TSI00223
    if 'ref_events' not in existing_tables:
        op.create_table(
            'ref_events',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('code', sa.Integer()),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('system_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now())
        )
        op.create_index('idx_ref_events_name', 'ref_events', ['name'])
        op.execute("""
        CREATE TRIGGER update_ref_events_updated_at BEFORE UPDATE ON ref_events 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
    
    # 11. Справочник типов элементов улично-дорожной сети - TSI00226
    if 'ref_street_types' not in existing_tables:
        op.create_table(
            'ref_street_types',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('code', sa.Integer()),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('system_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now())
        )
        op.create_index('idx_ref_street_types_name', 'ref_street_types', ['name'])
        op.execute("""
        CREATE TRIGGER update_ref_street_types_updated_at BEFORE UPDATE ON ref_street_types 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
    
    # 12. Справочник типов помещений - TSI00227
    if 'ref_room_types' not in existing_tables:
        op.create_table(
            'ref_room_types',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('code', sa.Integer()),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('system_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now())
        )
        op.create_index('idx_ref_room_types_name', 'ref_room_types', ['name'])
        op.execute("""
        CREATE TRIGGER update_ref_room_types_updated_at BEFORE UPDATE ON ref_room_types 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
    
    # 13. Справочник видов помещений - TSI00234
    if 'ref_room_categories' not in existing_tables:
        op.create_table(
            'ref_room_categories',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('code', sa.Integer()),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('system_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now())
        )
        op.create_index('idx_ref_room_categories_name', 'ref_room_categories', ['name'])
        op.execute("""
        CREATE TRIGGER update_ref_room_categories_updated_at BEFORE UPDATE ON ref_room_categories 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
    
    # 14. Справочник типов населенных пунктов - TSI00239
    if 'ref_settlement_types' not in existing_tables:
        op.create_table(
            'ref_settlement_types',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('code', sa.Integer()),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('system_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now())
        )
        op.create_index('idx_ref_settlement_types_name', 'ref_settlement_types', ['name'])
        op.execute("""
        CREATE TRIGGER update_ref_settlement_types_updated_at BEFORE UPDATE ON ref_settlement_types 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
    
    # 15. Справочник видов документов - TSI00206
    if 'ref_document_types' not in existing_tables:
        op.create_table(
            'ref_document_types',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('code', sa.Integer()),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('system_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now())
        )
        op.create_index('idx_ref_document_types_name', 'ref_document_types', ['name'])
        op.execute("""
        CREATE TRIGGER update_ref_document_types_updated_at BEFORE UPDATE ON ref_document_types 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
    
    # 16. Справочник валют - TSI00204
    if 'ref_currencies' not in existing_tables:
        op.create_table(
            'ref_currencies',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('code', sa.Integer()),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('system_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now())
        )
        op.create_index('idx_ref_currencies_name', 'ref_currencies', ['name'])
        op.execute("""
        CREATE TRIGGER update_ref_currencies_updated_at BEFORE UPDATE ON ref_currencies 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
    
    # 17. Справочник должностей - TSI00207
    if 'ref_positions' not in existing_tables:
        op.create_table(
            'ref_positions',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('code', sa.Integer()),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('system_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now())
        )
        op.create_index('idx_ref_positions_name', 'ref_positions', ['name'])
        op.execute("""
        CREATE TRIGGER update_ref_positions_updated_at BEFORE UPDATE ON ref_positions 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
    
    # 18. Справочник ОПФ (организационно-правовые формы) - TSI00203
    if 'ref_opf' not in existing_tables:
        op.create_table(
            'ref_opf',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('code', sa.Integer()),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('system_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now())
        )
        op.create_index('idx_ref_opf_name', 'ref_opf', ['name'])
        op.execute("""
        CREATE TRIGGER update_ref_opf_updated_at BEFORE UPDATE ON ref_opf 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
    
    # Add company fields if not already present
    if 'egr_companies' in existing_tables:
        columns = [c['name'] for c in inspector.get_columns('egr_companies')]
        
        if 'creation_method_id' not in columns:
            op.add_column('egr_companies', sa.Column('creation_method_id', sa.Integer(), nullable=True))
            op.create_foreign_key('fk_egr_companies_creation_method_id_ref_creation_methods', 
                                  'egr_companies', 'ref_creation_methods', 
                                  ['creation_method_id'], ['id'])
        
        if 'creation_decision_no' not in columns:
            op.add_column('egr_companies', sa.Column('creation_decision_no', sa.String(), nullable=True))
        
        if 'creation_authority_id' not in columns:
            op.add_column('egr_companies', sa.Column('creation_authority_id', sa.Integer(), nullable=True))
            op.create_foreign_key('fk_egr_companies_creation_authority_id_ref_authorities', 
                                  'egr_companies', 'ref_authorities', 
                                  ['creation_authority_id'], ['id'])
        
        if 'current_authority_id' not in columns:
            op.add_column('egr_companies', sa.Column('current_authority_id', sa.Integer(), nullable=True))
            op.create_foreign_key('fk_egr_companies_current_authority_id_ref_authorities', 
                                  'egr_companies', 'ref_authorities', 
                                  ['current_authority_id'], ['id'])
        
        if 'entity_type_id' not in columns:
            op.add_column('egr_companies', sa.Column('entity_type_id', sa.Integer(), nullable=True))
            op.create_foreign_key('fk_egr_companies_entity_type_id_ref_entity_types', 
                                  'egr_companies', 'ref_entity_types', 
                                  ['entity_type_id'], ['id'])
    
    # Create egr_company_events table
    if 'egr_company_events' not in existing_tables:
        op.create_table(
            'egr_company_events',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('event_record_id', sa.Integer(), nullable=True),
            sa.Column('event_type_id', sa.Integer(), nullable=True),
            sa.Column('event_date', sa.Date(), nullable=True),
            sa.Column('cancel_date', sa.Date(), nullable=True),
            sa.Column('document_date', sa.Date(), nullable=True),
            sa.Column('document_number', sa.String(), nullable=True),
            sa.Column('decision_authority_id', sa.Integer(), nullable=True),
            sa.Column('document_authority_id', sa.Integer(), nullable=True),
            sa.Column('foundation_id', sa.Integer(), nullable=True),
            sa.Column('deadline_date', sa.Date(), nullable=True),
            sa.Column('suspension_end_date', sa.Date(), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['company_id'], ['egr_companies.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['decision_authority_id'], ['ref_authorities.id']),
            sa.ForeignKeyConstraint(['document_authority_id'], ['ref_authorities.id']),
            sa.ForeignKeyConstraint(['event_type_id'], ['ref_events.id']),
            sa.ForeignKeyConstraint(['foundation_id'], ['ref_foundations.id']),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('idx_egr_company_events_company_id', 'egr_company_events', ['company_id'])
        op.create_index('idx_egr_company_events_event_type_id', 'egr_company_events', ['event_type_id'])
        op.create_index('idx_egr_company_events_event_date', 'egr_company_events', ['event_date'])


def downgrade() -> None:
    # Drop in reverse order
    op.drop_table('egr_company_events')
    
    # Remove added columns from egr_companies
    with op.batch_alter_table('egr_companies') as batch_op:
        batch_op.drop_constraint('fk_egr_companies_entity_type_id_ref_entity_types', type_='foreignkey')
        batch_op.drop_constraint('fk_egr_companies_current_authority_id_ref_authorities', type_='foreignkey')
        batch_op.drop_constraint('fk_egr_companies_creation_authority_id_ref_authorities', type_='foreignkey')
        batch_op.drop_constraint('fk_egr_companies_creation_method_id_ref_creation_methods', type_='foreignkey')
        batch_op.drop_column('entity_type_id')
        batch_op.drop_column('current_authority_id')
        batch_op.drop_column('creation_authority_id')
        batch_op.drop_column('creation_decision_no')
        batch_op.drop_column('creation_method_id')
    
    # Drop reference tables
    op.drop_table('ref_opf')
    op.drop_table('ref_positions')
    op.drop_table('ref_currencies')
    op.drop_table('ref_document_types')
    op.drop_table('ref_settlement_types')
    op.drop_table('ref_room_categories')
    op.drop_table('ref_room_types')
    op.drop_table('ref_street_types')
    op.drop_table('ref_events')
    op.drop_table('ref_foundations')
    op.drop_table('ref_soato')
    op.drop_table('ref_countries')
    op.drop_table('ref_ved')


