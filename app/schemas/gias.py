"""Schemas for GIAS registry endpoints."""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


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
