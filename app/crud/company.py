"""CRUD operations for companies"""
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_
from app.database.models import (
    Company,
    CompanyNameHistory,
    CompanyAddressHistory,
    CompanyVEDHistory,
    CompanyContactHistory,
    SyncHistory,
    RawCompanyData,
)
from datetime import datetime


class CompanyCRUD:
    """CRUD operations for Company entity"""
    
    def __init__(self, db: Session):
        self.db = db

    def get_by_unp(self, unp: int) -> Optional[Company]:
        """Get company by UNP"""
        return self.db.query(Company).filter(Company.unp == unp).first()

    def save_full_company_data(self, data: Dict[str, Any]) -> Company:
        """Save or update complete company data"""
        company_data = data["company"]
        unp = company_data["unp"]
        
        # Get or create company
        company = self.get_by_unp(unp)
        if not company:
            company = Company(**company_data)
            self.db.add(company)
            try:
                self.db.flush()
            except IntegrityError:
                self.db.rollback()
                company = self.get_by_unp(unp)
                if not company:
                    raise
        else:
            for key, value in company_data.items():
                if key != "unp":
                    setattr(company, key, value)
            self.db.add(company)  # FIXED: Explicitly mark as modified
            self.db.flush()
        
        # Save names history
        self._save_names_history(company, data.get("names", []))
        
        # Save addresses history
        self._save_addresses_history(company, data.get("addresses", []))
        
        # Save VED history
        self._save_ved_history(company, data.get("ved", []))
        
        # Save contacts history
        self._save_contacts_history(company, data.get("contacts", []))
        
        self.db.commit()
        return company

    def _save_names_history(self, company: Company, names: List[Dict]):
        """Save names history"""
        for name_data in names:
            # Check if exists
            existing = self.db.query(CompanyNameHistory).filter(
                and_(
                    CompanyNameHistory.company_id == company.id,
                    CompanyNameHistory.full_name_ru == name_data.get("full_name_ru"),
                    CompanyNameHistory.valid_from == name_data.get("valid_from")
                )
            ).first()
            
            if not existing:
                name_entry = CompanyNameHistory(
                    company_id=company.id,
                    **name_data
                )
                self.db.add(name_entry)

    def _save_addresses_history(self, company: Company, addresses: List[Dict]):
        """Save addresses history"""
        for addr_data in addresses:
            existing = self.db.query(CompanyAddressHistory).filter(
                and_(
                    CompanyAddressHistory.company_id == company.id,
                    CompanyAddressHistory.full_address == addr_data.get("full_address"),
                    CompanyAddressHistory.valid_from == addr_data.get("valid_from")
                )
            ).first()
            
            if not existing:
                addr_entry = CompanyAddressHistory(
                    company_id=company.id,
                    **addr_data
                )
                self.db.add(addr_entry)

    def _save_ved_history(self, company: Company, ved_list: List[Dict]):
        """Save VED history"""
        for ved_data in ved_list:
            existing = self.db.query(CompanyVEDHistory).filter(
                and_(
                    CompanyVEDHistory.company_id == company.id,
                    CompanyVEDHistory.ved_code == ved_data.get("ved_code"),
                    CompanyVEDHistory.valid_from == ved_data.get("valid_from")
                )
            ).first()
            
            if not existing:
                ved_entry = CompanyVEDHistory(
                    company_id=company.id,
                    **ved_data
                )
                self.db.add(ved_entry)

    def _save_contacts_history(self, company: Company, contacts: List[Dict]):
        """Save contacts history"""
        for contact_data in contacts:
            existing = self.db.query(CompanyContactHistory).filter(
                and_(
                    CompanyContactHistory.company_id == company.id,
                    CompanyContactHistory.email == contact_data.get("email"),
                    CompanyContactHistory.valid_from == contact_data.get("valid_from")
                )
            ).first()
            
            if not existing:
                contact_entry = CompanyContactHistory(
                    company_id=company.id,
                    **contact_data
                )
                self.db.add(contact_entry)

    def get_full_dossier(self, unp: int) -> Optional[Dict[str, Any]]:
        """Get full company dossier with all history"""
        company = self.get_by_unp(unp)
        if not company:
            return None

        def _pick_current_name(name_items: List[CompanyNameHistory]) -> Dict[str, Optional[str]]:
            if not name_items:
                return {"current_name_ru": None, "current_short_name_ru": None, "current_name_by": None}
            # Prefer active (valid_to is NULL), then most recent by valid_to/valid_from
            sorted_items = sorted(
                name_items,
                key=lambda n: (
                    n.valid_to is None,
                    n.valid_to or datetime.min.date(),
                    n.valid_from or datetime.min.date(),
                ),
                reverse=True,
            )
            current = sorted_items[0]
            return {
                "current_name_ru": current.full_name_ru,
                "current_short_name_ru": current.short_name_ru,
                "current_name_by": current.full_name_by,
            }

        current_name_fields = _pick_current_name(company.names_history)

        if not current_name_fields["current_name_ru"]:
            raw_entry = self.db.query(RawCompanyData).filter(RawCompanyData.unp == unp).first()
            if raw_entry:
                data = raw_entry.data or {}
                base_info = data.get("base_info") or {}
                common_info = data.get("common_info") or {}
                current_name_fields["current_name_ru"] = (
                    base_info.get("VNAIM")
                    or base_info.get("VFIO")
                    or common_info.get("fullNameRus")
                    or common_info.get("shortNameRus")
                )
                current_name_fields["current_short_name_ru"] = (
                    common_info.get("shortNameRus")
                    or base_info.get("VNAIM")
                )
                current_name_fields["current_name_by"] = (
                    base_info.get("VNAIMBY")
                    or common_info.get("fullNameBel")
                )

        return {
            "unp": company.unp,
            "current_status_code": company.current_status_code,
            "registration_date": company.registration_date.isoformat() if company.registration_date else None,
            "liquidation_date": company.liquidation_date.isoformat() if company.liquidation_date else None,
            **current_name_fields,
            "names": [
                {
                    "full_name_ru": n.full_name_ru,
                    "short_name_ru": n.short_name_ru,
                    "full_name_by": n.full_name_by,
                    "valid_from": n.valid_from.isoformat() if n.valid_from else None,
                    "valid_to": n.valid_to.isoformat() if n.valid_to else None,
                }
                for n in company.names_history
            ],
            "addresses": [
                {
                    "full_address": a.full_address,
                    "postal_code": a.postal_code,
                    "region": a.region,
                    "district": a.district,
                    "valid_from": a.valid_from.isoformat() if a.valid_from else None,
                    "valid_to": a.valid_to.isoformat() if a.valid_to else None,
                }
                for a in company.addresses_history
            ],
            "ved": [
                {
                    "ved_code": v.ved_code,
                    "ved_name": v.ved_name,
                    "valid_from": v.valid_from.isoformat() if v.valid_from else None,
                    "valid_to": v.valid_to.isoformat() if v.valid_to else None,
                }
                for v in company.ved_history
            ],
            "contacts": [
                {
                    "email": c.email,
                    "website": c.website,
                    "phone": c.phone,
                    "fax": c.fax,
                }
                for c in company.contacts_history
            ],
        }

    def log_sync(self, company_id: str, sync_type: str, status: str, changes_detected: bool = False, details: Dict = None):
        """Log synchronization"""
        sync_log = SyncHistory(
            company_id=company_id,
            sync_type=sync_type,
            sync_date=datetime.now(),
            changes_detected=changes_detected,
            status=status,
            details=details
        )
        self.db.add(sync_log)
        self.db.commit()






