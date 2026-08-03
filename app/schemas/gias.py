"""Schemas for GIAS registry endpoints."""
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class GiasSyncRunSchema(BaseModel):
    registry_name: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    records_fetched: int
    created_count: int
    updated_count: int
    unchanged_count: int
    history_created_count: int
    error: Optional[str] = None

    class Config:
        from_attributes = True


class GiasAccreditedCustomerSchema(BaseModel):
    unp: str
    name: str
    uid_customer: Optional[str] = None
    customer_id: Optional[str] = None
    summary: Optional[str] = None
    state: Optional[str] = None
    dt_update: Optional[datetime] = None
    dt_from: Optional[datetime] = None
    dt_to: Optional[datetime] = None
    is_customer: Optional[bool] = None
    is_organizator: Optional[bool] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    web_site: Optional[str] = None
    region: Optional[int] = None
    city_name: Optional[str] = None
    placements_address: Optional[str] = None
    placements_country: Optional[str] = None
    placements_post_index: Optional[str] = None
    placements_city: Optional[str] = None
    placements_address_detail: Optional[str] = None
    okogu_name: Optional[str] = None
    okogu_code: Optional[int] = None
    first_seen_at: datetime
    last_seen_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class GiasAccreditedCustomerHistorySchema(BaseModel):
    unp: str
    change_type: str
    changed_fields: Optional[dict[str, Any]] = None
    observed_at: datetime

    class Config:
        from_attributes = True


class LockedSupplierSchema(BaseModel):
    uuid: str
    chain_uuid: str
    state: str
    name: str
    provider_unp: Optional[str] = None
    location: Optional[str] = None
    reg_number: Optional[str] = None
    add_date: Optional[datetime] = None
    del_date: Optional[datetime] = None
    base_incl_text: Optional[str] = None
    base_excl_text: Optional[str] = None
    author_initials: Optional[str] = None
    author_summary: Optional[str] = None
    first_seen_at: datetime
    last_seen_at: datetime
    updated_at: Optional[datetime] = None


class LockedSupplierHistorySchema(BaseModel):
    provider_unp: Optional[str] = None
    supplier_name: str
    change_type: str
    changed_fields: Optional[dict[str, Any]] = None
    state: str
    location: Optional[str] = None
    reg_number: Optional[str] = None
    add_date: Optional[datetime] = None
    del_date: Optional[datetime] = None
    base_incl_text: Optional[str] = None
    base_excl_text: Optional[str] = None
    observed_at: datetime

    class Config:
        from_attributes = True


class GiasSyncTriggerResponse(BaseModel):
    status: str
    task_id: Optional[str] = None
    result: Optional[dict[str, Any]] = None


class GiasContractPositionSchema(BaseModel):
    id: UUID
    public_number: Optional[str] = None
    title: Optional[str] = None
    lot_number: Optional[int] = None
    lot_title: Optional[str] = None
    okpb_code: Optional[str] = None
    okpb_name: Optional[str] = None
    volume: Optional[Decimal] = None
    unit_code: Optional[str] = None
    unit_name: Optional[str] = None
    unit_symbol: Optional[str] = None
    position_type: Optional[str] = None
    unit_price: Optional[Decimal] = None
    position_price: Optional[Decimal] = None
    countries: Optional[list[str]] = None
    country_names: Optional[list[str]] = None
    is_smp: Optional[bool] = None

    class Config:
        from_attributes = True


class GiasContractAccountSchema(BaseModel):
    id: int
    company_id: Optional[UUID] = None
    company_unp: Optional[int] = None
    account_number: Optional[str] = None
    bank_code: Optional[str] = None
    bank_name: Optional[str] = None
    currency_code: Optional[str] = None
    currency_name: Optional[str] = None
    source_created_at: Optional[datetime] = None
    source_updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class GiasContractSchema(BaseModel):
    contract_id: UUID
    base_contract_id: Optional[UUID] = None
    chain_uuid: Optional[UUID] = None
    customer_company_id: Optional[UUID] = None
    provider_company_id: Optional[UUID] = None
    customer_unp: Optional[int] = None
    provider_unp: Optional[int] = None
    customer_name: Optional[str] = None
    customer_location: Optional[str] = None
    provider_name: Optional[str] = None
    provider_address: Optional[str] = None
    provider_country_name: Optional[str] = None
    state: Optional[str] = None
    state_asfr: Optional[str] = None
    title: Optional[str] = None
    price: Optional[Decimal] = None
    currency_code: Optional[str] = None
    plan_number: Optional[str] = None
    contract_number: Optional[str] = None
    registration_number: Optional[str] = None
    contract_type: Optional[str] = None
    ets_id: Optional[str] = None
    contract_date: Optional[datetime] = None
    execution_term: Optional[datetime] = None
    real_execution_term: Optional[datetime] = None
    termination_execution_term: Optional[datetime] = None
    termination_reason: Optional[str] = None
    has_smp: Optional[bool] = None
    source_created_at: Optional[datetime] = None
    source_updated_at: Optional[datetime] = None
    detail_status: str
    detail_fetched_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class GiasContractDetailSchema(GiasContractSchema):
    """Contract card including the lossless response from the GIAS detail API."""

    positions: list[GiasContractPositionSchema] = Field(default_factory=list)
    accounts: list[GiasContractAccountSchema] = Field(default_factory=list)
    raw_detail: Optional[dict[str, Any]] = None
    detail_last_error: Optional[str] = None
