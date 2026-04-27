"""add search index outbox queue

Revision ID: l5m6n7o8p9
Revises: k4l5m6n7o8
Create Date: 2026-04-27 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "l5m6n7o8p9"
down_revision = "k4l5m6n7o8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "search_index_queue",
        sa.Column("unp", sa.BigInteger(), nullable=False),
        sa.Column("operation", sa.String(length=20), nullable=False, server_default="index"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("enqueued_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("indexed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("unp"),
    )
    op.create_index(
        "ix_search_index_queue_status_updated_at",
        "search_index_queue",
        ["status", "updated_at"],
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enqueue_company_search_index_by_company()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                INSERT INTO search_index_queue (unp, operation, status, attempts, last_error, updated_at)
                VALUES (OLD.unp, 'delete', 'pending', 0, NULL, now())
                ON CONFLICT (unp) DO UPDATE SET
                    operation = 'delete',
                    status = 'pending',
                    attempts = 0,
                    last_error = NULL,
                    updated_at = now();
                RETURN OLD;
            END IF;

            IF TG_OP = 'UPDATE' AND OLD.unp IS DISTINCT FROM NEW.unp THEN
                INSERT INTO search_index_queue (unp, operation, status, attempts, last_error, updated_at)
                VALUES (OLD.unp, 'delete', 'pending', 0, NULL, now())
                ON CONFLICT (unp) DO UPDATE SET
                    operation = 'delete',
                    status = 'pending',
                    attempts = 0,
                    last_error = NULL,
                    updated_at = now();
            END IF;

            INSERT INTO search_index_queue (unp, operation, status, attempts, last_error, updated_at)
            VALUES (NEW.unp, 'index', 'pending', 0, NULL, now())
            ON CONFLICT (unp) DO UPDATE SET
                operation = 'index',
                status = 'pending',
                attempts = 0,
                last_error = NULL,
                updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_egr_companies_search_index
        AFTER INSERT OR UPDATE OR DELETE ON egr_companies
        FOR EACH ROW EXECUTE FUNCTION enqueue_company_search_index_by_company();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enqueue_company_search_index_by_name()
        RETURNS trigger AS $$
        DECLARE
            target_company_id uuid;
            target_unp bigint;
        BEGIN
            target_company_id := COALESCE(NEW.company_id, OLD.company_id);

            SELECT unp INTO target_unp
            FROM egr_companies
            WHERE id = target_company_id;

            IF target_unp IS NULL THEN
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END IF;

            INSERT INTO search_index_queue (unp, operation, status, attempts, last_error, updated_at)
            VALUES (target_unp, 'index', 'pending', 0, NULL, now())
            ON CONFLICT (unp) DO UPDATE SET
                operation = 'index',
                status = 'pending',
                attempts = 0,
                last_error = NULL,
                updated_at = now();

            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_egr_company_names_history_search_index
        AFTER INSERT OR UPDATE OR DELETE ON egr_company_names_history
        FOR EACH ROW EXECUTE FUNCTION enqueue_company_search_index_by_name();
        """
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_egr_company_names_history_search_index ON egr_company_names_history")
    op.execute("DROP FUNCTION IF EXISTS enqueue_company_search_index_by_name()")
    op.execute("DROP TRIGGER IF EXISTS trg_egr_companies_search_index ON egr_companies")
    op.execute("DROP FUNCTION IF EXISTS enqueue_company_search_index_by_company()")
    op.drop_index("ix_search_index_queue_status_updated_at", table_name="search_index_queue")
    op.drop_table("search_index_queue")
