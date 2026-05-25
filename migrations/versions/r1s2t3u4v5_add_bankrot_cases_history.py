"""add bankrot_cases_history table and audit trigger

Revision ID: r1s2t3u4v5
Revises: p9q0r1s2t3
Create Date: 2026-05-25 00:00:00.000000

Создаёт:
  - таблицу bankrot_cases_history — хранит предыдущие версии строк
  - функцию bankrot_cases_archive_history() — копирует OLD в history
  - триггер trg_bankrot_cases_history — вызывает функцию BEFORE UPDATE

При откате (downgrade):
  - удаляет триггер, функцию и таблицу
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "r1s2t3u4v5"
down_revision = "p9q0r1s2t3"
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------ #
    # bankrot_cases_history                                                #
    # ------------------------------------------------------------------ #
    op.create_table(
        "bankrot_cases_history",
        sa.Column("history_id",       sa.Integer(),    primary_key=True, autoincrement=True, nullable=False),
        sa.Column("case_id",          sa.Integer(),    nullable=False),
        sa.Column("debtor_unp",       sa.BigInteger(), nullable=True),
        sa.Column("number",           sa.Text(),       nullable=True),
        sa.Column("start_date",       sa.Date(),       nullable=True),
        sa.Column("end_date",         sa.Date(),       nullable=True),
        sa.Column("status",           sa.Integer(),    nullable=True),
        sa.Column("procedure_type",   sa.Integer(),    nullable=True),
        sa.Column("court",            sa.Text(),       nullable=True),
        sa.Column("judge",            sa.Text(),       nullable=True),
        sa.Column("manager_id",       sa.Integer(),    nullable=True),
        sa.Column("manager_name",     sa.Text(),       nullable=True),
        sa.Column("last_judgment_id", sa.BigInteger(), nullable=True),
        sa.Column("list_data",        postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("detail_data",      postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("judgements_group", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fetch_error",      sa.Text(),       nullable=True),
        sa.Column("case_created_at",  sa.DateTime(),   nullable=True),
        sa.Column("case_updated_at",  sa.DateTime(),   nullable=True),
        sa.Column("recorded_at",      sa.DateTime(),   server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_bankrot_cases_history_case_id",     "bankrot_cases_history", ["case_id"])
    op.create_index("idx_bankrot_cases_history_recorded_at", "bankrot_cases_history", ["recorded_at"])

    # ------------------------------------------------------------------ #
    # Триггерная функция                                                   #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE OR REPLACE FUNCTION bankrot_cases_archive_history()
        RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO bankrot_cases_history (
                case_id, debtor_unp, number, start_date, end_date,
                status, procedure_type, court, judge,
                manager_id, manager_name, last_judgment_id,
                list_data, detail_data, judgements_group,
                fetch_error, case_created_at, case_updated_at
            ) VALUES (
                OLD.case_id, OLD.debtor_unp, OLD.number, OLD.start_date, OLD.end_date,
                OLD.status, OLD.procedure_type, OLD.court, OLD.judge,
                OLD.manager_id, OLD.manager_name, OLD.last_judgment_id,
                OLD.list_data, OLD.detail_data, OLD.judgements_group,
                OLD.fetch_error, OLD.created_at, OLD.updated_at
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # ------------------------------------------------------------------ #
    # Триггер                                                              #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TRIGGER trg_bankrot_cases_history
        BEFORE UPDATE ON bankrot_cases
        FOR EACH ROW
        EXECUTE FUNCTION bankrot_cases_archive_history();
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_bankrot_cases_history ON bankrot_cases;")
    op.execute("DROP FUNCTION IF EXISTS bankrot_cases_archive_history();")

    op.drop_index("idx_bankrot_cases_history_recorded_at", table_name="bankrot_cases_history")
    op.drop_index("idx_bankrot_cases_history_case_id",     table_name="bankrot_cases_history")
    op.drop_table("bankrot_cases_history")
