"""EGR int64 event ids, event idempotency and IP-to-legal-entity links.

No historical dates are shifted blindly: mapper repairs them from source raw.
Existing duplicate event ids intentionally block index creation, not get deleted.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "egrapi2"
down_revision = "sourcefetch1"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("egr_company_events", "event_record_id", existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=True)
    op.create_index("uq_egr_event_source", "egr_company_events", ["company_id", "event_record_id"],
                    unique=True, postgresql_where=sa.text("event_record_id IS NOT NULL"))
    op.create_table("egr_ip_to_jur",
        sa.Column("ip_unp", sa.BigInteger(), primary_key=True),
        sa.Column("jur_unp", sa.BigInteger(), primary_key=True),
        sa.Column("registration_date", sa.Date(), nullable=True),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    # Refuse narrowing when it would overflow, or dropping populated links.
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM egr_ip_to_jur LIMIT 1")).first():
        raise RuntimeError("Export IP-to-Jur links before an explicitly approved destructive downgrade")
    if bind.execute(sa.text("SELECT 1 FROM egr_company_events WHERE event_record_id > 2147483647 OR event_record_id < -2147483648 LIMIT 1")).first():
        raise RuntimeError("Cannot narrow EGR event ids to int32 without data loss")
    op.drop_table("egr_ip_to_jur")
    op.drop_index("uq_egr_event_source", table_name="egr_company_events")
    op.alter_column("egr_company_events", "event_record_id", existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=True)
