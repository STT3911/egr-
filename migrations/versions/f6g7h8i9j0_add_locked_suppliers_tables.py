"""Add locked suppliers tables

Revision ID: f6g7h8i9j0
Revises: e5f6g7h8i9
Create Date: 2026-03-06 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f6g7h8i9j0"
down_revision = "e5f6g7h8i9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "locked_supplier_authors",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("initials", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "locked_supplier_reasons",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint(
        "locked_supplier_reasons_kind_text_uniq",
        "locked_supplier_reasons",
        ["kind", "text"],
    )

    op.create_table(
        "locked_suppliers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("chain_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", sa.BigInteger(), sa.ForeignKey("locked_supplier_authors.id"), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("provider_unp", sa.String(length=32), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("reg_number", sa.String(length=32), nullable=True),
        sa.Column("add_date", sa.DateTime(), nullable=True),
        sa.Column("del_date", sa.DateTime(), nullable=True),
        sa.Column("base_incl_id", sa.BigInteger(), sa.ForeignKey("locked_supplier_reasons.id"), nullable=True),
        sa.Column("base_excl_id", sa.BigInteger(), sa.ForeignKey("locked_supplier_reasons.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_index(
        "locked_suppliers_provider_unp_idx",
        "locked_suppliers",
        ["provider_unp"],
    )
    op.create_index(
        "locked_suppliers_state_idx",
        "locked_suppliers",
        ["state"],
    )


def downgrade() -> None:
    op.drop_index("locked_suppliers_state_idx", table_name="locked_suppliers")
    op.drop_index("locked_suppliers_provider_unp_idx", table_name="locked_suppliers")
    op.drop_table("locked_suppliers")
    op.drop_constraint(
        "locked_supplier_reasons_kind_text_uniq",
        "locked_supplier_reasons",
        type_="unique",
    )
    op.drop_table("locked_supplier_reasons")
    op.drop_table("locked_supplier_authors")

