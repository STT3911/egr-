"""Schemas for the Bitrix24 integration (thin requisite endpoint)."""

from pydantic import BaseModel
from typing import Optional


class BitrixRequisiteAddress(BaseModel):
    """Минимальный адрес для заполнения реквизита (юридический адрес)."""
    full_address: Optional[str] = None
    postal_code: Optional[int] = None
    region: Optional[str] = None


class BitrixRequisiteData(BaseModel):
    """
    «Тонкий» срез данных компании только под заполнение реквизитов Битрикс24.

    Сознательно не повторяет общий профиль компании: отдаёт ровно те поля,
    которые нужны приложению, чтобы создать/обновить реквизит.
    """
    unp: int
    is_ip: bool = False
    full_name: Optional[str] = None
    short_name: Optional[str] = None
    director: Optional[str] = None
    authority: Optional[str] = None
    registration_date: Optional[str] = None
    okved: Optional[str] = None
    address: Optional[BitrixRequisiteAddress] = None

    class Config:
        from_attributes = True
