"""
Models for Bitrix24 integration.
"""

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.bitrix.database import Base


class AppSettings(Base):
    """Bitrix24 application settings model."""
    
    __tablename__ = "bitrix_app_settings"
    
    # PK без sequence — id новым порталам назначаем вручную (app.bitrix.tenancy.next_settings_id).
    # default=1 убран: иначе вторая запись пыталась бы занять тот же id=1.
    id = Column(Integer, primary_key=True, index=True)
    
    # Bitrix24 connection
    bitrix_domain = Column(String(255), nullable=True)
    bitrix_member_id = Column(String(100), nullable=True)
    
    # Для безопасной валидации вебхуков (Опционально, но рекомендуется)
    application_token = Column(String(255), nullable=True)
    
    # OAuth tokens
    access_token = Column(String(512), nullable=True)
    refresh_token = Column(String(512), nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # App settings (Основная конфигурация)
    requisite_preset_id = Column(Integer, nullable=True)
    requisite_preset_name = Column(String(255), nullable=True)
    unp_field_code = Column(String(100), nullable=True)
    unp_field_label = Column(String(255), nullable=True)
    
    # Маски для ИП (IP Templates)
    ip_mask_full = Column(
        String(255), 
        default="Индивидуальный предприниматель {company_name}",
        nullable=True
    )
    ip_mask_short = Column(
        String(255), 
        default="ИП {company_name}",
        nullable=True
    )
    ip_mask_basis = Column(
        String(255), 
        default="Свидетельство о регистрации № {company_unp}",
        nullable=True
    )
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())