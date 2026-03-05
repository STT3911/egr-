import psycopg2
from psycopg2.extras import RealDictCursor
import logging
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
import os
from .models import PlanDetail, PurchaseItem, SyncLog

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        self.connection = None
        self.connect()
        self.create_tables()

    def connect(self):
        try:
            self.connection = psycopg2.connect(
                host=os.getenv('DB_HOST', 'db'),
                port=os.getenv('DB_PORT', '5432'),
                database=os.getenv('DB_NAME', 'tendex'),
                user=os.getenv('DB_USER', 'postgres'),
                password=os.getenv('DB_PASSWORD', ''),
            )
            self.connection.autocommit = False
            logger.info("Connected to database")
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise

    def create_tables(self):
        """Create all necessary tables if they don't exist"""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS gias_plans (
                uuid UUID PRIMARY KEY,
                dt_create TIMESTAMP,
                dt_update TIMESTAMP,
                state VARCHAR(50),
                post_date TIMESTAMP,
                version INTEGER,
                id_number VARCHAR(100),
                unp VARCHAR(20),
                name_of_company TEXT,
                year INTEGER,
                approve_person TEXT,
                post_person TEXT,
                approve_date TIMESTAMP,
                chain_uuid UUID,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS gias_plans_companies (
                unp VARCHAR(20) PRIMARY KEY,
                company_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS gias_okrb_0081995 (
                code VARCHAR(50) PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS gias_okrb_0072012 (
                code VARCHAR(50) PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS gias_plans_items (
                uuid UUID PRIMARY KEY,
                plan_chain_uuid UUID NOT NULL,
                public_number VARCHAR(100),
                goods_name TEXT,
                okrb_0072012_code VARCHAR(50),
                okrb_0081995_code VARCHAR(50),
                unit_code VARCHAR(50),
                unit_name TEXT,
                type VARCHAR(50),
                approx_value DECIMAL(20,2),
                budget_cost DECIMAL(20,2),
                fund_cost DECIMAL(20,2),
                inner_cost DECIMAL(20,2),
                fin_year INTEGER,
                procedure_month VARCHAR(100),
                search_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS gias_plans_items_changes (
                id SERIAL PRIMARY KEY,
                gias_plans_items_id UUID NOT NULL,
                event VARCHAR(20) NOT NULL,
                processed TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS gias_sync_log (
                id SERIAL PRIMARY KEY,
                sync_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                year INTEGER,
                type VARCHAR(50),
                pages_processed INTEGER DEFAULT 0,
                new_plans INTEGER DEFAULT 0,
                updated_plans INTEGER DEFAULT 0,
                new_items INTEGER DEFAULT 0,
                updated_items INTEGER DEFAULT 0,
                deleted_plans INTEGER DEFAULT 0,
                duration_seconds FLOAT DEFAULT 0,
                status VARCHAR(50),
                error_message TEXT
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_gias_plans_chain_uuid ON gias_plans(chain_uuid)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_gias_plans_dt_update ON gias_plans(dt_update DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_gias_plans_year ON gias_plans(year)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_gias_plans_items_chain_uuid ON gias_plans_items(plan_chain_uuid)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_gias_plans_items_changes_processed ON gias_plans_items_changes(processed) WHERE processed IS NULL
            """
        ]

        try:
            with self.connection.cursor() as cursor:
                # Serialize DDL to avoid deadlocks when multiple workers start together
                cursor.execute("SELECT pg_advisory_lock(2147483001)")
                try:
                    for query in queries:
                        cursor.execute(query)
                    # Ensure new columns exist for units (for already existing tables)
                    cursor.execute("""
                        ALTER TABLE gias_plans_items
                        ADD COLUMN IF NOT EXISTS unit_code VARCHAR(50)
                    """)
                    cursor.execute("""
                        ALTER TABLE gias_plans_items
                        ADD COLUMN IF NOT EXISTS unit_name TEXT
                    """)
                finally:
                    cursor.execute("SELECT pg_advisory_unlock(2147483001)")
                self.connection.commit()
                logger.info("Tables created/verified")
        except Exception as e:
            self.connection.rollback()
            logger.error(f"Error creating tables: {e}")
            raise

    def save_plan(self, plan: PlanDetail, dt_create: datetime, dt_update: datetime,
                  post_date: datetime, approve_date: Optional[datetime]) -> bool:
        """Save or update plan in database according to GIAS doc"""
        try:
            with self.connection.cursor() as cursor:
                # Handle versioning - mark old versions as OLD
                if plan.version > 1:
                    cursor.execute(
                        "UPDATE gias_plans SET state = 'OLD' WHERE chain_uuid = %s",
                        (plan.chainUuid,)
                    )

                # Insert or update plan
                cursor.execute("""
                    INSERT INTO gias_plans (
                        uuid, dt_create, dt_update, state, post_date, version,
                        id_number, unp, name_of_company, year, approve_person,
                        post_person, approve_date, chain_uuid
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (uuid) DO UPDATE SET
                        dt_update = EXCLUDED.dt_update,
                        state = EXCLUDED.state,
                        post_date = EXCLUDED.post_date,
                        version = EXCLUDED.version,
                        id_number = EXCLUDED.id_number,
                        approve_person = EXCLUDED.approve_person,
                        post_person = EXCLUDED.post_person,
                        approve_date = EXCLUDED.approve_date,
                        name_of_company = EXCLUDED.name_of_company,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING uuid
                """, (
                    plan.uuid, dt_create, dt_update, plan.state, post_date,
                    plan.version, plan.identificationNumber, plan.unp,
                    plan.nameOfCompany, plan.year, plan.approvePerson,
                    plan.postPerson, approve_date, plan.chainUuid
                ))

                # Collect existing items to enqueue delete events before removal
                cursor.execute(
                    "SELECT uuid FROM gias_plans_items WHERE plan_chain_uuid = %s",
                    (plan.chainUuid,)
                )
                existing_items = [row[0] for row in cursor.fetchall()]

                if existing_items:
                    cursor.executemany(
                        """
                        INSERT INTO gias_plans_items_changes (gias_plans_items_id, event)
                        VALUES (%s, 'delete')
                        """,
                        [(item,) for item in existing_items]
                    )

                # Delete old items before inserting new ones
                cursor.execute(
                    "DELETE FROM gias_plans_items WHERE plan_chain_uuid = %s",
                    (plan.chainUuid,)
                )

                # Save purchases
                for purchase in plan.purchases:
                    self._save_purchase(cursor, purchase, plan.chainUuid)

                self.connection.commit()
                return True

        except Exception as e:
            self.connection.rollback()
            logger.error(f"Error saving plan {plan.uuid}: {e}")
            return False

    def _save_purchase(self, cursor, purchase: PurchaseItem, plan_chain_uuid: str):
        """Save purchase item and related data"""
        # Save OKRB codes
        if purchase.okrb0081995Code:
            name_008 = purchase.okrb0081995Name or purchase.okrb0081995Code
            cursor.execute("""
                INSERT INTO gias_okrb_0081995 (code, name)
                VALUES (%s, %s)
                ON CONFLICT (code) DO NOTHING
            """, (purchase.okrb0081995Code, name_008))

        if purchase.okrb0072012Code:
            name_007 = purchase.okrb0072012Name or purchase.okrb0072012Code
            cursor.execute("""
                INSERT INTO gias_okrb_0072012 (code, name)
                VALUES (%s, %s)
                ON CONFLICT (code) DO NOTHING
            """, (purchase.okrb0072012Code, name_007))

        # Calculate financial totals
        budget_cost = 0
        fund_cost = 0
        inner_cost = 0
        fin_year = 0

        for cost in purchase.approximateCosts:
            budget_cost += cost.budgetCost
            fund_cost += cost.fundCost
            inner_cost += cost.innerCost
            fin_year = cost.finYear

        # Process months
        month_str_arr = [str(m) for m in purchase.procedureMonths]

        # Normalize search text
        search_text = self.normalize_search_text(purchase.goodsName)

        # Insert purchase item
        cursor.execute("""
            INSERT INTO gias_plans_items (
                uuid, plan_chain_uuid, public_number, goods_name,
                okrb_0072012_code, okrb_0081995_code, unit_code, unit_name, type, approx_value,
                budget_cost, fund_cost, inner_cost, fin_year,
                procedure_month, search_text
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            purchase.id, plan_chain_uuid, purchase.publicNumber,
            purchase.goodsName, purchase.okrb0072012Code,
            purchase.okrb0081995Code, purchase.unitCode, purchase.unitName, purchase.type,
            purchase.approximateValue, budget_cost, fund_cost,
            inner_cost, fin_year, ",".join(month_str_arr), search_text
        ))

        # Create change record for Elasticsearch
        cursor.execute("""
            INSERT INTO gias_plans_items_changes (gias_plans_items_id, event)
            VALUES (%s, 'create')
        """, (purchase.id,))

    @staticmethod
    def normalize_search_text(text: str) -> str:
        """Normalize text for search according to GIAS documentation"""
        if not text:
            return ""

        # Replace ё with е
        text = text.replace('ё', 'е').replace('Ё', 'Е')

        # Convert to lowercase
        text = text.lower()

        # Replace hyphens with underscores per doc
        text = text.replace('-', '_')

        # Remove special characters
        for char in ':!?\'()"«»;,.':
            text = text.replace(char, ' ')

        # Replace multiple spaces with single space
        import re
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    def log_sync(self, log: SyncLog):
        """Log synchronization result"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO gias_sync_log (
                        sync_time, year, type, pages_processed, new_plans,
                        updated_plans, new_items, updated_items, deleted_plans,
                        duration_seconds, status, error_message
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    log.sync_time or datetime.now(), log.year, log.type,
                    log.pages_processed, log.new_plans, log.updated_plans,
                    log.new_items, log.updated_items, log.deleted_plans,
                    log.duration_seconds, log.status, log.error_message
                ))
                self.connection.commit()
        except Exception as e:
            logger.error(f"Error logging sync: {e}")

    def get_max_updated_date(self) -> Optional[datetime]:
        """Get maximum dt_update from plans"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT MAX(dt_update) FROM gias_plans"
                )
                result = cursor.fetchone()
                return result[0] if result[0] else None
        except Exception as e:
            logger.error(f"Error getting max updated date: {e}")
            return None

    def get_existing_plan_uuids(self, year: int) -> Set[str]:
        """Get set of existing plan UUIDs for a year"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT uuid FROM gias_plans WHERE year = %s",
                    (year,)
                )
                return {row[0] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Error getting existing UUIDs: {e}")
            return set()

    def close(self):
        if self.connection:
            self.connection.close()