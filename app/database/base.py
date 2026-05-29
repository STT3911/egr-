"""Database base"""
from app.core.database import Base

# Import all models here for Alembic to detect them
from app.database.models import (
    SystemState,
    SearchIndexQueue,
    RawCompanyData,
    Company,
    CompanyPlaceLocation,
    CompanyNameHistory,
    CompanyAddressHistory,
    CompanyVEDHistory,
    CompanyContactHistory,
    SyncHistory,
    ApiLog,
    NalogDebtRecord,
    TradeRegistryRecord,
    TradeRegistryImportRun,
    TradeRegistryImportStage,
    PVTResidentRecord,
    EAEUSEZResidentRecord,
    GiasSyncRun,
    GiasAccreditedCustomer,
    GiasAccreditedCustomerHistory,
    LockedSupplierAuthor,
    LockedSupplierReason,
    LockedSupplier,
    LockedSupplierHistory,
)

__all__ = [
    "Base",
    "SystemState",
    "SearchIndexQueue",
    "RawCompanyData",
    "Company",
    "CompanyPlaceLocation",
    "CompanyNameHistory",
    "CompanyAddressHistory",
    "CompanyVEDHistory",
    "CompanyContactHistory",
    "SyncHistory",
    "ApiLog",
    "NalogDebtRecord",
    "TradeRegistryRecord",
    "TradeRegistryImportRun",
    "TradeRegistryImportStage",
    "PVTResidentRecord",
    "EAEUSEZResidentRecord",
    "GiasSyncRun",
    "GiasAccreditedCustomer",
    "GiasAccreditedCustomerHistory",
    "LockedSupplierAuthor",
    "LockedSupplierReason",
    "LockedSupplier",
    "LockedSupplierHistory",
]



