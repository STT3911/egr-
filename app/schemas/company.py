"""Company schemas"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import date


class CompanyNameSchema(BaseModel):
    """Company name schema"""
    full_name_ru: Optional[str] = None
    short_name_ru: Optional[str] = None
    full_name_by: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None


class CompanyAddressSchema(BaseModel):
    """Company address schema"""
    full_address: Optional[str] = None
    postal_code: Optional[int] = None
    region: Optional[str] = None
    district: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None


class CompanyVEDSchema(BaseModel):
    """Company VED schema"""
    ved_code: Optional[str] = None
    ved_name: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None


class CompanyContactSchema(BaseModel):
    """Company contact schema"""
    email: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None


class CompanyProfileResponse(BaseModel):
    """Company full profile response"""
    unp: int
    current_status_code: Optional[int] = None
    registration_date: Optional[str] = None
    liquidation_date: Optional[str] = None
    current_name_ru: Optional[str] = None
    current_short_name_ru: Optional[str] = None
    current_name_by: Optional[str] = None
    names: List[CompanyNameSchema] = []
    addresses: List[CompanyAddressSchema] = []
    ved: List[CompanyVEDSchema] = []
    contacts: List[CompanyContactSchema] = []

    class Config:
        from_attributes = True


class CompanyLookupItem(BaseModel):
    """Company lookup item for autocomplete"""
    unp: int
    name: Optional[str] = None
    full_name_ru: Optional[str] = None
    short_name_ru: Optional[str] = None
    full_name_by: Optional[str] = None


class CompanyLookupResponse(BaseModel):
    """Company lookup response"""
    query: str
    count: int
    results: List[CompanyLookupItem] = []






