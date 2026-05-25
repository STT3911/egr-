"""add bankrot_cases and bankrot_sync_runs tables

Revision ID: p9q0r1s2t3
Revises: o8p9q0r1s2
Create Date: 2026-05-25 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "p9q0r1s2t3"
down_revision = "o8p9q0r1s2"
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------ #
    # bankrot_cases                                                        #
    # ------------------------------------------------------------------ #
    op.create_table(
        "bankrot_cases",
        sa.Column("case_id", sa.Integer(), primary_key=True, nullable=False),
        # Мягкая связь с egr_companies (без FK — компании может не быть в ЕГР)
        sa.Column("debtor_unp", sa.BigInteger(), nullable=True),
        # Основные поля дела
        sa.Column("number", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.Integer(), nullable=True),
        sa.Column("procedure_type", sa.Integer(), nullable=True),
        sa.Column("court", sa.Text(), nullable=True),
        sa.Column("judge", sa.Text(), nullable=True),
        # Управляющий
        sa.Column("manager_id", sa.Integer(), nullable=True),
        sa.Column("manager_name", sa.Text(), nullable=True),
        sa.Column("last_judgment_id", sa.BigInteger(), nullable=True),
        # Сырые ответы API
        sa.Column("list_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("detail_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("judgements_group", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Ошибки частичной загрузки
        sa.Column("fetch_error", sa.Text(), nullable=True),
        # Метаданные
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_bankrot_cases_debtor_unp", "bankrot_cases", ["debtor_unp"])
    op.create_index("idx_bankrot_cases_start_date", "bankrot_cases", ["start_date"])
    op.create_index("idx_bankrot_cases_status", "bankrot_cases", ["status"])
    op.create_index("idx_bankrot_cases_manager_id", "bankrot_cases", ["manager_id"])

    # ------------------------------------------------------------------ #
    # bankrot_sync_runs                                                    #
    # ------------------------------------------------------------------ #
    op.create_table(
        "bankrot_sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("total_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_page", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_file", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("stats_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index("idx_bankrot_sync_runs_status", "bankrot_sync_runs", ["status"])


def downgrade():
    op.drop_index("idx_bankrot_sync_runs_status", table_name="bankrot_sync_runs")
    op.drop_table("bankrot_sync_runs")

    op.drop_index("idx_bankrot_cases_manager_id", table_name="bankrot_cases")
    op.drop_index("idx_bankrot_cases_status", table_name="bankrot_cases")
    op.drop_index("idx_bankrot_cases_start_date", table_name="bankrot_cases")
    op.drop_index("idx_bankrot_cases_debtor_unp", table_name="bankrot_cases")
    op.drop_table("bankrot_cases")
