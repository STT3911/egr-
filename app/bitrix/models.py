"""
Models for Bitrix24 integration.
"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from app.bitrix.database import Base


class AppSettings(Base):
    """Bitrix24 application settings model."""
    
    __tablename__ = "bitrix_app_settings"
    
    id = Column(Integer, primary_key=True, index=True, default=1)
    
    # Bitrix24 connection
    bitrix_domain = Column(String(255), nullable=True)
    bitrix_member_id = Column(String(100), nullable=True)
    
    # OAuth tokens
    access_token = Column(String(512), nullable=True)
    refresh_token = Column(String(512), nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    
    # App settings
    requisite_preset_id = Column(Integer, nullable=True)
    requisite_preset_name = Column(String(255), nullable=True)
    unp_field_code = Column(String(100), nullable=True)
    unp_field_label = Column(String(255), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
