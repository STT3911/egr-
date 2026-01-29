"""Pydantic schemas for reference tables"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ReferenceBaseSchema(BaseModel):
    """Base schema for all reference types"""
    id: int
    name: str
    system_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ReferenceWithCodeSchema(ReferenceBaseSchema):
    """Schema for references with code field"""
    code: Optional[int] = None


class ReferenceStatusSchema(ReferenceBaseSchema):
    """Schema for ref_statuses (TSI00219)"""
    pass


class ReferenceCreationMethodSchema(ReferenceBaseSchema):
    """Schema for ref_creation_methods (TSI00208)"""
    pass


class ReferenceEntityTypeSchema(ReferenceBaseSchema):
    """Schema for ref_entity_types (TSI00211)"""
    pass


class ReferenceAuthoritySchema(ReferenceBaseSchema):
    """Schema for ref_authorities (TSI00212)"""
    pass


class ReferenceLiquidationMethodSchema(ReferenceBaseSchema):
    """Schema for ref_liquidation_methods (TSI00228)"""
    pass


class ReferenceVEDSchema(BaseModel):
    """Schema for ref_ved (TSI00114)"""
    id: int
    code: Optional[str] = None
    name: str
    system_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ReferenceCountrySchema(ReferenceWithCodeSchema):
    """Schema for ref_countries (TSI00201)"""
    pass


class ReferenceSOATOSchema(BaseModel):
    """Schema for ref_soato (TSI00202)"""
    id: int
    code: Optional[int] = None
    name: str
    object_number: Optional[int] = None
    system_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ReferenceFoundationSchema(ReferenceWithCodeSchema):
    """Schema for ref_foundations (TSI00213)"""
    pass


class ReferenceEventSchema(ReferenceWithCodeSchema):
    """Schema for ref_events (TSI00223)"""
    pass


class ReferenceStreetTypeSchema(ReferenceWithCodeSchema):
    """Schema for ref_street_types (TSI00226)"""
    pass


class ReferenceRoomTypeSchema(ReferenceWithCodeSchema):
    """Schema for ref_room_types (TSI00227)"""
    pass


class ReferenceRoomCategorySchema(ReferenceWithCodeSchema):
    """Schema for ref_room_categories (TSI00234)"""
    pass


class ReferenceSettlementTypeSchema(ReferenceWithCodeSchema):
    """Schema for ref_settlement_types (TSI00239)"""
    pass


class ReferenceDocumentTypeSchema(ReferenceWithCodeSchema):
    """Schema for ref_document_types (TSI00206)"""
    pass


class ReferenceCurrencySchema(ReferenceWithCodeSchema):
    """Schema for ref_currencies (TSI00204)"""
    pass


class ReferencePositionSchema(ReferenceWithCodeSchema):
    """Schema for ref_positions (TSI00207)"""
    pass


class ReferenceOPFSchema(ReferenceWithCodeSchema):
    """Schema for ref_opf (TSI00203)"""
    pass


