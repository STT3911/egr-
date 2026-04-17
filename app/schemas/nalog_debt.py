"""Schemas for tax debt data from portal.nalog.gov.by."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class NalogDebtRecordResponse(BaseModel):
    debtor_unp: int
    imns_code: str
    imns_name: Optional[str] = None
    debt_date: str
    repayment_date: str
    slice_date: str

    class Config:
        from_attributes = True


class CompanyNalogDebtResponse(BaseModel):
    unp: int
    count: int
    latest_slice_date: Optional[str] = None
    items: list[NalogDebtRecordResponse]

