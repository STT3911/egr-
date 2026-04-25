"""Link GIAS registries to main EGR companies table

Revision ID: j3k4l5m6n7
Revises: i2j3k4l5m6
Create Date: 2026-04-24 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "j3k4l5m6n7"
down_revision = "i2j3k4l5m6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gias_accredited_customers",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_gias_accredited_customers_company_id",
        "gias_accredited_customers",
        "egr_companies",
        ["company_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_gias_accredited_customers_company_id", "gias_accredited_customers", ["company_id"], unique=True)

    op.add_column(
        "gias_accredited_customers_history",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_gias_accredited_customers_history_company_id",
        "gias_accredited_customers_history",
        "egr_companies",
        ["company_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_gias_accredited_customers_history_company_id",
        "gias_accredited_customers_history",
        ["company_id"],
    )

    op.add_column(
        "locked_suppliers",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_locked_suppliers_company_id",
        "locked_suppliers",
        "egr_companies",
        ["company_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_locked_suppliers_company_id", "locked_suppliers", ["company_id"])

    op.add_column(
        "locked_suppliers_history",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_locked_suppliers_history_company_id",
        "locked_suppliers_history",
        "egr_companies",
        ["company_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_locked_suppliers_history_company_id", "locked_suppliers_history", ["company_id"])

    op.execute(
        """
        UPDATE gias_accredited_customers gac
        SET company_id = c.id
        FROM egr_companies c
        WHERE c.unp::text = gac.unp
        """
    )
    op.execute(
        """
        UPDATE gias_accredited_customers_history h
        SET company_id = gac.company_id
        FROM gias_accredited_customers gac
        WHERE h.customer_id = gac.id
        """
    )
    op.execute(
        """
        UPDATE locked_suppliers ls
        SET company_id = c.id
        FROM egr_companies c
        WHERE ls.provider_unp ~ '^[0-9]+$' AND c.unp = CAST(ls.provider_unp AS bigint)
        """
    )
    op.execute(
        """
        UPDATE locked_suppliers_history h
        SET company_id = ls.company_id
        FROM locked_suppliers ls
        WHERE h.supplier_id = ls.id
        """
    )


def downgrade() -> None:
    op.drop_index("idx_locked_suppliers_history_company_id", table_name="locked_suppliers_history")
    op.drop_constraint("fk_locked_suppliers_history_company_id", "locked_suppliers_history", type_="foreignkey")
    op.drop_column("locked_suppliers_history", "company_id")

    op.drop_index("idx_locked_suppliers_company_id", table_name="locked_suppliers")
    op.drop_constraint("fk_locked_suppliers_company_id", "locked_suppliers", type_="foreignkey")
    op.drop_column("locked_suppliers", "company_id")

    op.drop_index("idx_gias_accredited_customers_history_company_id", table_name="gias_accredited_customers_history")
    op.drop_constraint(
        "fk_gias_accredited_customers_history_company_id",
        "gias_accredited_customers_history",
        type_="foreignkey",
    )
    op.drop_column("gias_accredited_customers_history", "company_id")

    op.drop_index("idx_gias_accredited_customers_company_id", table_name="gias_accredited_customers")
    op.drop_constraint(
        "fk_gias_accredited_customers_company_id",
        "gias_accredited_customers",
        type_="foreignkey",
    )
    op.drop_column("gias_accredited_customers", "company_id")
