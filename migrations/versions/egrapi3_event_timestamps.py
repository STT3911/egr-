"""Reconcile event audit columns omitted by the original events migration.

Existing timestamps are preserved. Old rows without audit timestamps stay
NULL: migration time must not pretend to be their historical creation time.
"""
from alembic import op

revision = "egrapi3"
down_revision = "egrapi2"
branch_labels = None
depends_on = None


def upgrade():
    # IF NOT EXISTS also supports installations created with ORM metadata,
    # where these columns already exist. Defaults apply only to future rows.
    for column in ("created_at", "updated_at"):
        op.execute(
            f"ALTER TABLE egr_company_events ADD COLUMN IF NOT EXISTS "
            f"{column} TIMESTAMP WITHOUT TIME ZONE NULL"
        )
        op.execute(
            f"ALTER TABLE egr_company_events ALTER COLUMN {column} SET DEFAULT now()"
        )


def downgrade():
    # A rollback cannot know whether this migration originally added the
    # columns or merely found them. Never drop pre-existing audit data.
    raise RuntimeError(
        "Event audit columns are retained for safety; rollback application code "
        "without downgrading egrapi3"
    )
