"""Add GIAS directory registries and history

Revision ID: i2j3k4l5m6
Revises: h1i2j3k4l5
Create Date: 2026-04-24 17:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "i2j3k4l5m6"
down_revision = "h1i2j3k4l5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "gias_sync_runs" not in existing_tables:
        op.create_table(
            "gias_sync_runs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("registry_name", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("started_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("records_fetched", sa.Integer(), server_default="0", nullable=False),
            sa.Column("created_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("updated_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("unchanged_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("history_created_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("idx_gias_sync_runs_registry_name", "gias_sync_runs", ["registry_name"])
        op.create_index("idx_gias_sync_runs_status", "gias_sync_runs", ["status"])

    if "gias_accredited_customers" not in existing_tables:
        op.create_table(
            "gias_accredited_customers",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("unp", sa.String(length=20), nullable=False, unique=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("uid_customer", sa.String(length=255), nullable=True),
            sa.Column("customer_id", sa.String(length=255), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("state", sa.String(length=50), nullable=True),
            sa.Column("dt_update", sa.DateTime(), nullable=True),
            sa.Column("dt_from", sa.DateTime(), nullable=True),
            sa.Column("dt_to", sa.DateTime(), nullable=True),
            sa.Column("is_customer", sa.Boolean(), nullable=True),
            sa.Column("is_organizator", sa.Boolean(), nullable=True),
            sa.Column("phone", sa.String(length=100), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("web_site", sa.String(length=255), nullable=True),
            sa.Column("region", sa.Integer(), nullable=True),
            sa.Column("city_name", sa.String(length=255), nullable=True),
            sa.Column("placements_address", sa.Text(), nullable=True),
            sa.Column("placements_country", sa.String(length=10), nullable=True),
            sa.Column("placements_post_index", sa.String(length=20), nullable=True),
            sa.Column("placements_city", sa.String(length=255), nullable=True),
            sa.Column("placements_address_detail", sa.Text(), nullable=True),
            sa.Column("okogu_name", sa.String(length=255), nullable=True),
            sa.Column("okogu_code", sa.Integer(), nullable=True),
            sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("sync_hash", sa.String(length=64), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("idx_gias_accredited_customers_unp", "gias_accredited_customers", ["unp"])
        op.create_index("idx_gias_accredited_customers_state", "gias_accredited_customers", ["state"])
        op.create_index("idx_gias_accredited_customers_last_seen", "gias_accredited_customers", ["last_seen_at"])

    if "gias_accredited_customers_history" not in existing_tables:
        op.create_table(
            "gias_accredited_customers_history",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "customer_id",
                sa.BigInteger(),
                sa.ForeignKey("gias_accredited_customers.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("unp", sa.String(length=20), nullable=False),
            sa.Column("change_type", sa.String(length=20), nullable=False),
            sa.Column("changed_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("observed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(
            "idx_gias_accredited_customers_history_customer_id",
            "gias_accredited_customers_history",
            ["customer_id"],
        )
        op.create_index(
            "idx_gias_accredited_customers_history_unp",
            "gias_accredited_customers_history",
            ["unp"],
        )
        op.create_index(
            "idx_gias_accredited_customers_history_observed_at",
            "gias_accredited_customers_history",
            ["observed_at"],
        )

    if "locked_suppliers" in existing_tables:
        locked_columns = {col["name"] for col in inspector.get_columns("locked_suppliers")}
        if "raw_json" not in locked_columns:
            op.add_column("locked_suppliers", sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        if "sync_hash" not in locked_columns:
            op.add_column("locked_suppliers", sa.Column("sync_hash", sa.String(length=64), nullable=True))
        if "first_seen_at" not in locked_columns:
            op.add_column(
                "locked_suppliers",
                sa.Column("first_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            )
        if "last_seen_at" not in locked_columns:
            op.add_column(
                "locked_suppliers",
                sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            )
            op.create_index("idx_locked_suppliers_last_seen_at", "locked_suppliers", ["last_seen_at"])
        locked_indexes = {idx["name"] for idx in inspector.get_indexes("locked_suppliers")}
        if "idx_locked_suppliers_chain_uuid" not in locked_indexes:
            op.create_index("idx_locked_suppliers_chain_uuid", "locked_suppliers", ["chain_uuid"])

    if "locked_suppliers_history" not in existing_tables:
        op.create_table(
            "locked_suppliers_history",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "supplier_id",
                sa.BigInteger(),
                sa.ForeignKey("locked_suppliers.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("provider_unp", sa.String(length=32), nullable=True),
            sa.Column("supplier_name", sa.Text(), nullable=False),
            sa.Column("chain_uuid", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("change_type", sa.String(length=20), nullable=False),
            sa.Column("changed_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("state", sa.String(length=32), nullable=False),
            sa.Column("location", sa.Text(), nullable=True),
            sa.Column("reg_number", sa.String(length=32), nullable=True),
            sa.Column("add_date", sa.DateTime(), nullable=True),
            sa.Column("del_date", sa.DateTime(), nullable=True),
            sa.Column("base_incl_text", sa.Text(), nullable=True),
            sa.Column("base_excl_text", sa.Text(), nullable=True),
            sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("observed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("idx_locked_suppliers_history_supplier_id", "locked_suppliers_history", ["supplier_id"])
        op.create_index("idx_locked_suppliers_history_provider_unp", "locked_suppliers_history", ["provider_unp"])
        op.create_index("idx_locked_suppliers_history_chain_uuid", "locked_suppliers_history", ["chain_uuid"])
        op.create_index("idx_locked_suppliers_history_observed_at", "locked_suppliers_history", ["observed_at"])


def downgrade() -> None:
    op.drop_index("idx_locked_suppliers_history_observed_at", table_name="locked_suppliers_history")
    op.drop_index("idx_locked_suppliers_history_chain_uuid", table_name="locked_suppliers_history")
    op.drop_index("idx_locked_suppliers_history_provider_unp", table_name="locked_suppliers_history")
    op.drop_index("idx_locked_suppliers_history_supplier_id", table_name="locked_suppliers_history")
    op.drop_table("locked_suppliers_history")

    inspector = sa.inspect(op.get_bind())
    locked_indexes = {idx["name"] for idx in inspector.get_indexes("locked_suppliers")}
    if "idx_locked_suppliers_chain_uuid" in locked_indexes:
        op.drop_index("idx_locked_suppliers_chain_uuid", table_name="locked_suppliers")
    if "idx_locked_suppliers_last_seen_at" in locked_indexes:
        op.drop_index("idx_locked_suppliers_last_seen_at", table_name="locked_suppliers")

    locked_columns = {col["name"] for col in inspector.get_columns("locked_suppliers")}
    if "last_seen_at" in locked_columns:
        op.drop_column("locked_suppliers", "last_seen_at")
    if "first_seen_at" in locked_columns:
        op.drop_column("locked_suppliers", "first_seen_at")
    if "sync_hash" in locked_columns:
        op.drop_column("locked_suppliers", "sync_hash")
    if "raw_json" in locked_columns:
        op.drop_column("locked_suppliers", "raw_json")

    op.drop_index(
        "idx_gias_accredited_customers_history_observed_at",
        table_name="gias_accredited_customers_history",
    )
    op.drop_index(
        "idx_gias_accredited_customers_history_unp",
        table_name="gias_accredited_customers_history",
    )
    op.drop_index(
        "idx_gias_accredited_customers_history_customer_id",
        table_name="gias_accredited_customers_history",
    )
    op.drop_table("gias_accredited_customers_history")

    op.drop_index("idx_gias_accredited_customers_last_seen", table_name="gias_accredited_customers")
    op.drop_index("idx_gias_accredited_customers_state", table_name="gias_accredited_customers")
    op.drop_index("idx_gias_accredited_customers_unp", table_name="gias_accredited_customers")
    op.drop_table("gias_accredited_customers")

    op.drop_index("idx_gias_sync_runs_status", table_name="gias_sync_runs")
    op.drop_index("idx_gias_sync_runs_registry_name", table_name="gias_sync_runs")
    op.drop_table("gias_sync_runs")
