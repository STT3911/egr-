"""fill bitrix_app_settings ip masks and application_token columns

Колонки ip_mask_* и application_token описаны в модели AppSettings и пишутся
из админки, но миграция c432bf1e9d9a, которая должна была их создать, осталась
пустой (upgrade = pass). Без этих колонок сохранение масок ИП падает.

Добавляем колонки идемпотентно (ADD COLUMN IF NOT EXISTS), чтобы миграция была
безопасна и на инсталляциях, где их частично создавали вручную.

Revision ID: bx2masks01
Revises: f5g6h7i8j9
Create Date: 2026-06-17
"""
from alembic import op


revision = 'bx2masks01'
down_revision = 'f5g6h7i8j9'
branch_labels = None
depends_on = None


_DEFAULT_FULL = 'Индивидуальный предприниматель {company_name}'
_DEFAULT_SHORT = 'ИП {company_name}'
_DEFAULT_BASIS = 'Свидетельство о регистрации № {company_unp}'


def upgrade() -> None:
    op.execute(
        "ALTER TABLE bitrix_app_settings "
        "ADD COLUMN IF NOT EXISTS application_token VARCHAR(255)"
    )
    op.execute(
        "ALTER TABLE bitrix_app_settings "
        "ADD COLUMN IF NOT EXISTS ip_mask_full VARCHAR(255) "
        f"DEFAULT '{_DEFAULT_FULL}'"
    )
    op.execute(
        "ALTER TABLE bitrix_app_settings "
        "ADD COLUMN IF NOT EXISTS ip_mask_short VARCHAR(255) "
        f"DEFAULT '{_DEFAULT_SHORT}'"
    )
    op.execute(
        "ALTER TABLE bitrix_app_settings "
        "ADD COLUMN IF NOT EXISTS ip_mask_basis VARCHAR(255) "
        f"DEFAULT '{_DEFAULT_BASIS}'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE bitrix_app_settings DROP COLUMN IF EXISTS ip_mask_basis")
    op.execute("ALTER TABLE bitrix_app_settings DROP COLUMN IF EXISTS ip_mask_short")
    op.execute("ALTER TABLE bitrix_app_settings DROP COLUMN IF EXISTS ip_mask_full")
    op.execute("ALTER TABLE bitrix_app_settings DROP COLUMN IF EXISTS application_token")
