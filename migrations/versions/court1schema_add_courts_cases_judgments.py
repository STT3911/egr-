"""Add courts, source processes and their judicial decisions.

Revision ID: court1schema
Revises: addrunit1
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "court1schema"
down_revision = "addrunit1"
branch_labels = None
depends_on = None

# Frozen source dictionary. Never import changing application data in migrations.
COURTS = [
    {"id": 151, "name": "Экономический суд Брестской области"},
    {"id": 152, "name": "Экономический суд Витебской области"},
    {"id": 153, "name": "Экономический суд Гомельской области"},
    {"id": 154, "name": "Экономический суд Гродненской области"},
    {"id": 155, "name": "Экономический суд г. Минска"},
    {"id": 156, "name": "Экономический суд Минской области"},
    {"id": 157, "name": "Экономический суд Могилевской области"},
    {"id": 1, "name": "Судебная коллегия по экономическим делам Верховного Суда"},
]


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    courts = op.create_table(
        "courts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.Text(), nullable=False),
        *timestamps(),
    )
    op.bulk_insert(courts, COURTS)
    op.create_table(
        "court_cases",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("court_id", sa.Integer(), sa.ForeignKey("courts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_process_id", sa.BigInteger(), nullable=False),
        sa.Column("case_number", sa.Text(), nullable=False),
        sa.Column("raw_data", JSONB(), nullable=False, server_default="{}"),
        *timestamps(),
        sa.UniqueConstraint("court_id", "source_process_id", name="uq_court_cases_source"),
        sa.CheckConstraint("source_process_id > 0", name="ck_court_cases_process_positive"),
    )
    op.create_index("ix_court_cases_court_number", "court_cases", ["court_id", "case_number"])
    op.create_index("ix_court_cases_case_number", "court_cases", ["case_number"])
    op.create_table(
        "court_judgments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.BigInteger(), sa.ForeignKey("court_cases.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_document_id", sa.BigInteger(), nullable=False),
        sa.Column("document_type", sa.Text(), nullable=True),
        sa.Column("judgment_date", sa.Date(), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("download_url", sa.Text(), nullable=True),
        sa.Column("raw_data", JSONB(), nullable=False, server_default="{}"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        *timestamps(),
        sa.UniqueConstraint("case_id", "source_document_id", name="uq_court_judgments_source"),
        sa.CheckConstraint("source_document_id > 0", name="ck_court_judgments_document_positive"),
    )
    op.create_index("ix_court_judgments_judgment_date", "court_judgments", ["judgment_date"])
    op.create_index("ix_court_judgments_case_date", "court_judgments", ["case_id", "judgment_date"])


def downgrade() -> None:
    # Explicit rollback deletes only data introduced by this revision.
    op.drop_table("court_judgments")
    op.drop_table("court_cases")
    op.drop_table("courts")
