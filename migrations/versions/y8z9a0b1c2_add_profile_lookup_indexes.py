"""add profile lookup indexes

Revision ID: y8z9a0b1c2
Revises: x7y8z9a0b1
Create Date: 2026-06-04 15:00:00.000000
"""

from alembic import op


revision = "y8z9a0b1c2"
down_revision = "x7y8z9a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_egr_company_names_current_pick
        ON egr_company_names_history (
            company_id,
            (valid_to IS NULL) DESC,
            valid_to DESC NULLS LAST,
            valid_from DESC NULLS LAST
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_egr_company_addresses_current_pick
        ON egr_company_addresses_history (
            company_id,
            (valid_to IS NULL) DESC,
            valid_to DESC NULLS LAST,
            valid_from DESC NULLS LAST
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_trade_registry_records_profile_order
        ON trade_registry_records (
            unp,
            object_type ASC NULLS FIRST,
            object_name ASC NULLS FIRST,
            registration_number ASC
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_eaeu_sez_resident_records_profile_order
        ON eaeu_sez_resident_records (
            unp,
            sez_name ASC NULLS FIRST,
            item_id ASC
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_license_records_profile_order
        ON license_records (
            holder_unp,
            activity_is_active DESC NULLS LAST,
            last_seen_at DESC NULLS LAST,
            license_id DESC
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_inspection_plan_records_profile_order
        ON inspection_plan_records (
            subject_unp,
            plan_year DESC NULLS LAST,
            plan_half DESC NULLS LAST,
            start_month_no ASC NULLS LAST,
            plan_item_no ASC NULLS LAST,
            controller_authority ASC NULLS FIRST
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_belltpp_own_certificates_profile_order
        ON belltpp_own_certificates (
            holder_unp,
            valid_until DESC NULLS LAST,
            issue_date DESC NULLS LAST,
            cert_number ASC
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_bankrot_cases_profile_order
        ON bankrot_cases (
            debtor_unp,
            start_date DESC NULLS LAST
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_bankrot_cases_profile_order")
    op.execute("DROP INDEX IF EXISTS ix_belltpp_own_certificates_profile_order")
    op.execute("DROP INDEX IF EXISTS ix_inspection_plan_records_profile_order")
    op.execute("DROP INDEX IF EXISTS ix_license_records_profile_order")
    op.execute("DROP INDEX IF EXISTS ix_eaeu_sez_resident_records_profile_order")
    op.execute("DROP INDEX IF EXISTS ix_trade_registry_records_profile_order")
    op.execute("DROP INDEX IF EXISTS ix_egr_company_addresses_current_pick")
    op.execute("DROP INDEX IF EXISTS ix_egr_company_names_current_pick")
