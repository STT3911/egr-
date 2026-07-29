"""Expand ref_soato identifiers to BIGINT.

Revision ID: soato1bigint
Revises: giascontracts01
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa


revision = "soato1bigint"
down_revision = "giascontracts01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "ref_soato",
        "id",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )


def downgrade() -> None:
    connection = op.get_bind()
    out_of_range = connection.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM ref_soato
                WHERE id < -2147483648 OR id > 2147483647
            )
            """
        )
    ).scalar()
    if out_of_range:
        raise RuntimeError(
            "Cannot downgrade ref_soato.id to INTEGER while out-of-range IDs exist"
        )

    op.alter_column(
        "ref_soato",
        "id",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
    )
