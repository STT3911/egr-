"""Add reference tables

Revision ID: 80dada155a2c
Revises: 001_egr_initial
Create Date: 2026-01-08 11:55:30.295218

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '80dada155a2c'
down_revision = '001_egr_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create trigger function for auto-updating updated_at
    op.execute("""
    CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ language 'plpgsql';
    """)
    
    # 1. Справочник состояний (Статусы) - TSI00219
    op.create_table(
        'ref_statuses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('system_id', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now())
    )
    op.create_index('idx_ref_statuses_name', 'ref_statuses', ['name'])
    op.execute("""
    CREATE TRIGGER update_ref_statuses_updated_at BEFORE UPDATE ON ref_statuses 
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    
    # 2. Справочник способов создания - TSI00208
    op.create_table(
        'ref_creation_methods',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('system_id', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now())
    )
    op.create_index('idx_ref_creation_methods_name', 'ref_creation_methods', ['name'])
    op.execute("""
    CREATE TRIGGER update_ref_creation_methods_updated_at BEFORE UPDATE ON ref_creation_methods 
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    
    # 3. Справочник видов объектов (ЮЛ/ИП) - TSI00211
    op.create_table(
        'ref_entity_types',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('system_id', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now())
    )
    op.create_index('idx_ref_entity_types_name', 'ref_entity_types', ['name'])
    op.execute("""
    CREATE TRIGGER update_ref_entity_types_updated_at BEFORE UPDATE ON ref_entity_types 
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    
    # 4. Справочник органов (Исполкомы, Министерства) - TSI00212
    op.create_table(
        'ref_authorities',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('system_id', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now())
    )
    op.create_index('idx_ref_authorities_name', 'ref_authorities', ['name'])
    op.execute("""
    CREATE TRIGGER update_ref_authorities_updated_at BEFORE UPDATE ON ref_authorities 
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    
    # 5. Справочник способов исключения/ликвидации - TSI00228
    op.create_table(
        'ref_liquidation_methods',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('system_id', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now())
    )
    op.create_index('idx_ref_liquidation_methods_name', 'ref_liquidation_methods', ['name'])
    op.execute("""
    CREATE TRIGGER update_ref_liquidation_methods_updated_at BEFORE UPDATE ON ref_liquidation_methods 
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    
    # 6. Справочник видов экономической деятельности - TSI00114
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


def downgrade() -> None:
    # Drop tables in reverse order
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
    op.drop_table('ref_liquidation_methods')
    op.drop_table('ref_authorities')
    op.drop_table('ref_entity_types')
    op.drop_table('ref_creation_methods')
    op.drop_table('ref_statuses')
    
    # Drop trigger function
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;")






