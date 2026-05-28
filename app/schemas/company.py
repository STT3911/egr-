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


class CompanyGiasAccreditationSchema(BaseModel):
    state: Optional[str] = None
    summary: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    web_site: Optional[str] = None
    city_name: Optional[str] = None
    placements_address: Optional[str] = None
    dt_update: Optional[str] = None
    dt_from: Optional[str] = None
    dt_to: Optional[str] = None


class CompanyGiasLockedSupplierSchema(BaseModel):
    state: Optional[str] = None
    name: Optional[str] = None
    location: Optional[str] = None
    reg_number: Optional[str] = None
    add_date: Optional[str] = None
    del_date: Optional[str] = None
    base_incl_text: Optional[str] = None
    base_excl_text: Optional[str] = None
    author_initials: Optional[str] = None


class CompanyPVTResidentSchema(BaseModel):
    name: Optional[str] = None
    profile_url: Optional[str] = None
    description: Optional[str] = None
    source_url: Optional[str] = None
    city: Optional[str] = None
    legal_address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    activity_directions: List[str] = []
    list_description: Optional[str] = None
    last_seen_at: Optional[str] = None


class CompanyTradeRegistryRecordSchema(BaseModel):
    registration_number: Optional[str] = None
    legal_name: Optional[str] = None
    legal_address: Optional[str] = None
    object_type: Optional[str] = None
    object_name: Optional[str] = None
    internet_shop_domain: Optional[str] = None
    trade_network_name: Optional[str] = None
    object_region: Optional[str] = None
    object_district: Optional[str] = None
    object_locality: Optional[str] = None
    object_street: Optional[str] = None
    object_building: Optional[str] = None
    object_office: Optional[str] = None
    object_contacts: Optional[str] = None
    format_type: Optional[str] = None
    location_type: Optional[str] = None
    assortment_type: Optional[str] = None
    trade_object_type: Optional[str] = None
    trade_area: Optional[str] = None
    retail_trade: Optional[str] = None
    wholesale_trade: Optional[str] = None
    goods_groups: Optional[str] = None
    inclusion_date: Optional[str] = None
    source_date: Optional[str] = None
    source_file: Optional[str] = None
    last_seen_at: Optional[str] = None


class BankrotCaseSchema(BaseModel):
    """Краткая карточка дела о банкротстве для профиля компании."""
    case_id: int
    number: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[int] = None
    procedure_type: Optional[int] = None
    court: Optional[str] = None
    judge: Optional[str] = None
    manager_name: Optional[str] = None
    updated_at: Optional[str] = None


class CompanyProfileResponse(BaseModel):
    """Company full profile response"""
    unp: int
    current_status_code: Optional[int] = None
    current_status_name: Optional[str] = None
    registration_date: Optional[str] = None
    liquidation_date: Optional[str] = None
    current_name_ru: Optional[str] = None
    current_short_name_ru: Optional[str] = None
    place_location_address: Optional[str] = None
    current_name_by: Optional[str] = None
    names: List[CompanyNameSchema] = []
    addresses: List[CompanyAddressSchema] = []
    ved: List[CompanyVEDSchema] = []
    contacts: List[CompanyContactSchema] = []
    gias_accreditation: Optional[CompanyGiasAccreditationSchema] = None
    gias_locked_suppliers: List[CompanyGiasLockedSupplierSchema] = []
    pvt_resident: Optional[CompanyPVTResidentSchema] = None
    trade_registry_records: List[CompanyTradeRegistryRecordSchema] = []
    bankrot_cases: List[BankrotCaseSchema] = []

    class Config:
        from_attributes = True


class CompanyLookupItem(BaseModel):
    """Company lookup item for autocomplete"""
    unp: int
    name: Optional[str] = None
    full_name_ru: Optional[str] = None
    short_name_ru: Optional[str] = None
    full_name_by: Optional[str] = None
    matched_name: Optional[str] = None
    matched_historical_name: bool = False


class CompanyLookupResponse(BaseModel):
    """Company lookup response"""
    query: str
    count: int
    results: List[CompanyLookupItem] = []

