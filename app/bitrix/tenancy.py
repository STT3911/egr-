"""
Мультитенант: выбор настроек нужного портала Битрикс24.

Приложение может быть установлено на несколько порталов Б24. На каждый портал —
своя запись AppSettings (свои токены, свой конфиг реквизитов). Портал
идентифицируется по `member_id` (стабильный ID портала), с резервом по домену.

`select_tenant` — чистая функция выбора из готового списка (легко тестируется и
не тянет БД). Асинхронные хелперы ниже импортируют БД/модель внутри тел функций,
чтобы импорт `select_tenant` оставался лёгким.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.bitrix.models import AppSettings


def select_tenant(rows: "Iterable[AppSettings]", member_id=None, domain=None) -> "Optional[AppSettings]":
    """Выбрать настройки портала: сначала по member_id, затем (резерв) по домену.

    Возвращает None, если портал не найден — для вебхука это значит «чужой/
    неустановленный портал» (отклоняем), для клиента — настроек нет.
    """
    mid = str(member_id).strip() if member_id else ""
    dom = str(domain).strip() if domain else ""
    rows = list(rows)

    if mid:
        for r in rows:
            if r.bitrix_member_id and str(r.bitrix_member_id) == mid:
                return r
    if dom:
        for r in rows:
            if r.bitrix_domain and str(r.bitrix_domain) == dom:
                return r
    return None


async def find_settings(db: "AsyncSession", member_id=None, domain=None) -> "Optional[AppSettings]":
    """Найти AppSettings нужного портала. Таблица крошечная (одна строка на портал),
    поэтому грузим все и выбираем в памяти — единый источник логики (select_tenant)."""
    from sqlalchemy import select

    from app.bitrix.models import AppSettings

    rows = (await db.execute(select(AppSettings))).scalars().all()
    return select_tenant(rows, member_id, domain)


async def next_settings_id(db: "AsyncSession") -> int:
    """Следующий id для новой записи портала. У таблицы нет sequence (PK — обычный
    integer), поэтому id назначаем вручную как max(id)+1."""
    from sqlalchemy import func, select

    from app.bitrix.models import AppSettings

    result = await db.execute(select(func.max(AppSettings.id)))
    return (result.scalar() or 0) + 1
