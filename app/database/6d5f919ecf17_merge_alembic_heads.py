"""Merge alembic heads

Revision ID: 6d5f919ecf17
Revises: c432bf1e9d9a, g7h8i9j0k1
Create Date: 2026-04-10 17:41:19.855972

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6d5f919ecf17'
down_revision = ('c432bf1e9d9a', 'g7h8i9j0k1')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass



