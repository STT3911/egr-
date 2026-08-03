"""Normalize GIAS provider bank accounts and link them to companies.

Revision ID: giasacct1
Revises: giaswindow1
Create Date: 2026-08-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "giasacct1"
down_revision = "giaswindow1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gias_contract_accounts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("company_unp", sa.BigInteger(), nullable=True),
        sa.Column("account_number", sa.Text(), nullable=True),
        sa.Column("bank_code", sa.String(length=64), nullable=True),
        sa.Column("bank_name", sa.Text(), nullable=True),
        sa.Column("currency_code", sa.String(length=16), nullable=True),
        sa.Column("currency_name", sa.String(length=64), nullable=True),
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
            name="fk_gias_contract_accounts_contract",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["egr_companies.id"],
            name="fk_gias_contract_accounts_company",
            ondelete="SET NULL",
        ),
    )
    for name, columns in (
        ("idx_gias_contract_accounts_contract", ["contract_id"]),
        ("idx_gias_contract_accounts_company", ["company_id"]),
        ("idx_gias_contract_accounts_unp", ["company_unp"]),
        ("idx_gias_contract_accounts_source_updated", ["source_updated_at"]),
    ):
        op.create_index(name, "gias_contract_accounts", columns)

    # Existing detail cards will not necessarily be downloaded again soon, so
    # normalize their account arrays during deployment. The fallback covers
    # older GIAS responses where the same fields were stored at the top level.
    op.execute(
        """
        WITH account_source AS (
            SELECT
                c.contract_id,
                c.provider_company_id AS company_id,
                c.provider_unp AS company_unp,
                c.source_created_at,
                c.source_updated_at,
                account
            FROM gias_contracts AS c
            CROSS JOIN LATERAL jsonb_array_elements(
                CASE
                    WHEN jsonb_typeof(c.raw_detail -> 'contractAccounts') = 'array'
                    THEN CASE
                        WHEN jsonb_array_length(c.raw_detail -> 'contractAccounts') > 0
                        THEN c.raw_detail -> 'contractAccounts'
                        WHEN COALESCE(
                            NULLIF(BTRIM(c.raw_detail ->> 'accountProvider'), ''),
                            NULLIF(BTRIM(c.raw_detail ->> 'bankProviderCode'), ''),
                            NULLIF(BTRIM(c.raw_detail ->> 'bankProviderName'), '')
                        ) IS NOT NULL
                        THEN jsonb_build_array(c.raw_detail)
                        ELSE '[]'::jsonb
                    END
                    WHEN COALESCE(
                        NULLIF(BTRIM(c.raw_detail ->> 'accountProvider'), ''),
                        NULLIF(BTRIM(c.raw_detail ->> 'bankProviderCode'), ''),
                        NULLIF(BTRIM(c.raw_detail ->> 'bankProviderName'), '')
                    ) IS NOT NULL
                    THEN jsonb_build_array(c.raw_detail)
                    ELSE '[]'::jsonb
                END
            ) AS account
            WHERE c.raw_detail IS NOT NULL
        ), distinct_accounts AS (
            SELECT DISTINCT ON (
                contract_id,
                NULLIF(BTRIM(account ->> 'accountProvider'), ''),
                NULLIF(BTRIM(account ->> 'bankProviderCode'), ''),
                NULLIF(BTRIM(account ->> 'bankProviderName'), ''),
                NULLIF(BTRIM(account ->> 'accountProviderCurrencyCode'), ''),
                NULLIF(BTRIM(account ->> 'accountProviderCurrencyName'), '')
            )
                contract_id,
                company_id,
                company_unp,
                NULLIF(BTRIM(account ->> 'accountProvider'), '') AS account_number,
                NULLIF(BTRIM(account ->> 'bankProviderCode'), '') AS bank_code,
                NULLIF(BTRIM(account ->> 'bankProviderName'), '') AS bank_name,
                NULLIF(BTRIM(account ->> 'accountProviderCurrencyCode'), '') AS currency_code,
                NULLIF(BTRIM(account ->> 'accountProviderCurrencyName'), '') AS currency_name,
                source_created_at,
                source_updated_at,
                account AS raw_json
            FROM account_source
            WHERE COALESCE(
                NULLIF(BTRIM(account ->> 'accountProvider'), ''),
                NULLIF(BTRIM(account ->> 'bankProviderCode'), ''),
                NULLIF(BTRIM(account ->> 'bankProviderName'), ''),
                NULLIF(BTRIM(account ->> 'accountProviderCurrencyCode'), ''),
                NULLIF(BTRIM(account ->> 'accountProviderCurrencyName'), '')
            ) IS NOT NULL
        )
        INSERT INTO gias_contract_accounts (
            contract_id,
            company_id,
            company_unp,
            account_number,
            bank_code,
            bank_name,
            currency_code,
            currency_name,
            source_created_at,
            source_updated_at,
            raw_json
        )
        SELECT
            contract_id,
            company_id,
            company_unp,
            account_number,
            bank_code,
            bank_name,
            currency_code,
            currency_name,
            source_created_at,
            source_updated_at,
            raw_json
        FROM distinct_accounts
        """
    )


def downgrade() -> None:
    op.drop_table("gias_contract_accounts")
