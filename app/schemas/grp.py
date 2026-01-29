"""Schemas for MNS GRP taxpayer data."""

from pydantic import BaseModel
from typing import Optional, Any, Dict


class GrpTaxpayerDataResponse(BaseModel):
    """Normalized GRP taxpayer record returned by our API."""

    unp: int
    full_name: Optional[str] = None
    short_name: Optional[str] = None
    registration_date: Optional[str] = None
    inspectorate_code: Optional[str] = None
    inspectorate_name: Optional[str] = None
    status_code: Optional[str] = None
    status_date: Optional[str] = None
    address: Optional[str] = None

    fetched_at: Optional[str] = None
    updated_at: Optional[str] = None

    http_status: Optional[int] = None
    last_error: Optional[str] = None

    raw: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
