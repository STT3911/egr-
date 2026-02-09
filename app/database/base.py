"""Database base"""
from app.core.database import Base

# Import all models here for Alembic to detect them
from app.database.models import (
    SystemState,
    RawCompanyData,
    Company,
    CompanyNameHistory,
    CompanyAddressHistory,
    CompanyVEDHistory,
    CompanyContactHistory,
    SyncHistory,
    ApiLog,
    NalogDebtRecord,
)

__all__ = [
    "Base",
    "SystemState",
    "RawCompanyData",
    "Company",
    "CompanyNameHistory",
    "CompanyAddressHistory",
    "CompanyVEDHistory",
    "CompanyContactHistory",
    "SyncHistory",
    "ApiLog",
    "NalogDebtRecord",
]






