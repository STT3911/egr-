"""Add GIAS contracts, company links and normalized positions.

Revision ID: giascontracts01
Revises: unp1scan01
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "giascontracts01"
down_revision = "unp1scan01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gias_contracts",
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("base_contract_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("chain_uuid", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("customer_company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider_company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("customer_unp", sa.BigInteger(), nullable=True),
        sa.Column("provider_unp", sa.BigInteger(), nullable=True),
        sa.Column("customer_gias_uuid", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("customer_name", sa.Text(), nullable=True),
        sa.Column("customer_location", sa.Text(), nullable=True),
        sa.Column("customer_region", sa.Integer(), nullable=True),
        sa.Column("customer_city_name", sa.Text(), nullable=True),
        sa.Column("customer_okogu_code", sa.Integer(), nullable=True),
        sa.Column("provider_name", sa.Text(), nullable=True),
        sa.Column("provider_address", sa.Text(), nullable=True),
        sa.Column("provider_country", sa.String(length=8), nullable=True),
        sa.Column("provider_country_name", sa.String(length=255), nullable=True),
        sa.Column("state", sa.String(length=40), nullable=True),
        sa.Column("state_asfr", sa.String(length=40), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(20, 2), nullable=True),
        sa.Column("currency_code", sa.String(length=8), nullable=True),
        sa.Column("plan_number", sa.String(length=100), nullable=True),
        sa.Column("contract_number", sa.String(length=255), nullable=True),
        sa.Column("registration_number", sa.String(length=255), nullable=True),
        sa.Column("contract_type", sa.String(length=100), nullable=True),
        sa.Column("ets_id", sa.String(length=100), nullable=True),
        sa.Column("contract_date", sa.DateTime(), nullable=True),
        sa.Column("execution_term", sa.DateTime(), nullable=True),
        sa.Column("real_execution_term", sa.DateTime(), nullable=True),
        sa.Column("termination_execution_term", sa.DateTime(), nullable=True),
        sa.Column("termination_reason", sa.Text(), nullable=True),
        sa.Column("has_smp", sa.Boolean(), nullable=True),
        sa.Column("source_created_at", sa.DateTime(), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(), nullable=True),
        sa.Column(
            "raw_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("raw_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sync_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "detail_status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "detail_attempts", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("detail_last_error", sa.Text(), nullable=True),
        sa.Column("detail_next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("detail_fetched_at", sa.DateTime(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["customer_company_id"],
            ["egr_companies.id"],
            name="fk_gias_contracts_customer_company",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["provider_company_id"],
            ["egr_companies.id"],
            name="fk_gias_contracts_provider_company",
            ondelete="SET NULL",
        ),
    )
    for name, columns in (
        ("idx_gias_contracts_base_contract", ["base_contract_id"]),
        ("idx_gias_contracts_chain", ["chain_uuid"]),
        ("idx_gias_contracts_customer_company", ["customer_company_id"]),
        ("idx_gias_contracts_provider_company", ["provider_company_id"]),
        ("idx_gias_contracts_customer_unp", ["customer_unp"]),
        ("idx_gias_contracts_provider_unp", ["provider_unp"]),
        ("idx_gias_contracts_state", ["state"]),
        ("idx_gias_contracts_plan_number", ["plan_number"]),
        ("idx_gias_contracts_registration_number", ["registration_number"]),
        ("idx_gias_contracts_contract_date", ["contract_date"]),
        ("idx_gias_contracts_source_updated", ["source_updated_at"]),
        ("idx_gias_contracts_detail_status", ["detail_status"]),
        ("idx_gias_contracts_detail_next_retry", ["detail_next_retry_at"]),
    ):
        op.create_index(name, "gias_contracts", columns)

    op.create_table(
        "gias_contract_sync_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "next_page", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("total_pages", sa.Integer(), nullable=True),
        sa.Column(
            "initial_complete",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "gias_contract_positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_number", sa.String(length=100), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("lot_uuid", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lot_number", sa.Integer(), nullable=True),
        sa.Column("lot_title", sa.Text(), nullable=True),
        sa.Column("okpb_uuid", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("okpb_code", sa.String(length=64), nullable=True),
        sa.Column("okpb_name", sa.Text(), nullable=True),
        sa.Column("volume", sa.Numeric(24, 6), nullable=True),
        sa.Column("unit_uuid", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("unit_code", sa.String(length=32), nullable=True),
        sa.Column("unit_name", sa.String(length=255), nullable=True),
        sa.Column("unit_symbol", sa.String(length=64), nullable=True),
        sa.Column("position_type", sa.String(length=100), nullable=True),
        sa.Column("unit_price", sa.Numeric(20, 2), nullable=True),
        sa.Column("position_price", sa.Numeric(20, 2), nullable=True),
        sa.Column("countries", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "country_names", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("is_smp", sa.Boolean(), nullable=True),
        sa.Column("source_created_at", sa.DateTime(), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(), nullable=True),
        sa.Column(
            "raw_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["gias_contracts.contract_id"],
            name="fk_gias_contract_positions_contract",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_gias_contract_positions_contract",
        "gias_contract_positions",
        ["contract_id"],
    )
    op.create_index(
        "idx_gias_contract_positions_public_number",
        "gias_contract_positions",
        ["public_number"],
    )
    op.create_index(
        "idx_gias_contract_positions_okpb_code",
        "gias_contract_positions",
        ["okpb_code"],
    )


def downgrade() -> None:
    op.drop_table("gias_contract_positions")
    op.drop_table("gias_contract_sync_state")
    op.drop_table("gias_contracts")
