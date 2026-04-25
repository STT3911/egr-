"""CRUD operations for companies"""
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.database.models import (
    Company,
    CompanyNameHistory,
    CompanyAddressHistory,
    CompanyVEDHistory,
    CompanyContactHistory,
    SyncHistory,
    RawCompanyData,
    CompanyPlaceLocation,
    GiasAccreditedCustomer,
    LockedSupplier,
)
from datetime import datetime
from app.utils.search_normalizer import normalize_company_name

# Ref tables used by egr_companies FK — insert placeholder if missing to avoid ForeignKeyViolation
_REF_TABLE_NAMES = (
    "ref_creation_methods",
    "ref_authorities",
    "ref_entity_types",
    "ref_liquidation_methods",
)


class CompanyCRUD:
    """CRUD operations for Company entity"""
    
    def __init__(self, db: Session):
        self.db = db

    def get_by_unp(self, unp: int) -> Optional[Company]:
        """Get company by UNP"""
        return self.db.query(Company).filter(Company.unp == unp).first()

    def _ensure_ref_id(self, table: str, ref_id: Optional[int], default_name_prefix: str) -> None:
        """Insert placeholder row into ref table if id is missing (ON CONFLICT DO NOTHING)."""
        if ref_id is None or table not in _REF_TABLE_NAMES:
            return
        default_name = f"{default_name_prefix} {ref_id}"
        stmt = text(
            f"INSERT INTO {table} (id, name, system_id) VALUES (:id, :name, NULL) ON CONFLICT (id) DO NOTHING"
        )
        self.db.execute(stmt, {"id": ref_id, "name": default_name})

    def _ensure_ref_ids_for_company(self, company_data: Dict[str, Any]) -> None:
        """Ensure all ref FK ids used by company exist in ref tables (insert placeholder if missing)."""
        self._ensure_ref_id(
            "ref_creation_methods",
            company_data.get("creation_method_id"),
            "Способ создания",
        )
        self._ensure_ref_id(
            "ref_authorities",
            company_data.get("creation_authority_id"),
            "Орган",
        )
        self._ensure_ref_id(
            "ref_authorities",
            company_data.get("current_authority_id"),
            "Орган",
        )
        self._ensure_ref_id(
            "ref_authorities",
            company_data.get("liquidation_authority_id"),
            "Орган",
        )
        self._ensure_ref_id(
            "ref_entity_types",
            company_data.get("entity_type_id"),
            "Тип объекта",
        )
        self._ensure_ref_id(
            "ref_liquidation_methods",
            company_data.get("liquidation_reason_id"),
            "Способ ликвидации",
        )

    def save_full_company_data(self, data: Dict[str, Any]) -> Company:
        """Save or update complete company data"""
        company_data = data["company"]
        unp = company_data["unp"]

        # Ensure ref tables have rows for all FK ids (avoids ForeignKeyViolation when update_reference_tables missed some)
        self._ensure_ref_ids_for_company(company_data)
        self.db.flush()
        
        # Надёжный upsert по UNP без гонок:
        # всегда выполняем INSERT ... ON CONFLICT (unp) DO UPDATE.
        # При обновлении не трогаем поле id, чтобы не ломать внешние ключи.
        stmt = pg_insert(Company).values(**company_data).on_conflict_do_update(
            index_elements=[Company.unp],
            set_={k: v for k, v in company_data.items() if k not in ("unp", "id")},
        )
        self.db.execute(stmt)
        self.db.flush()
        company = self.get_by_unp(unp)
        
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
        """Save names history with automatic search_name generation"""
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
                # Автоматически генерируем search_name для умного поиска
                full_name = name_data.get("full_name_ru") or name_data.get("short_name_ru") or name_data.get("full_name_by")
                search_name = normalize_company_name(full_name) if full_name else None
                
                name_entry = CompanyNameHistory(
                    company_id=company.id,
                    search_name=search_name,  # Умный поиск
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

    def _pick_current_name(self, name_items) -> Dict[str, Optional[str]]:
        if not name_items:
            return {"current_name_ru": None, "current_short_name_ru": None, "current_name_by": None}
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

    def get_full_dossier(self, unp: int) -> Optional[Dict[str, Any]]:
        """Get full company dossier — optimized, single query"""
        company = (
            self.db.query(Company)
            .options(
                selectinload(Company.names_history),
                selectinload(Company.addresses_history),
                selectinload(Company.ved_history),
                selectinload(Company.contacts_history),
                selectinload(Company.gias_accreditation),
                selectinload(Company.gias_locked_suppliers).selectinload(LockedSupplier.author),
                selectinload(Company.gias_locked_suppliers).selectinload(LockedSupplier.base_incl),
                selectinload(Company.gias_locked_suppliers).selectinload(LockedSupplier.base_excl),
            )
            .filter(Company.unp == unp)
            .first()
        )

        if not company:
            return None

        # Статус
        status_name = None
        if company.current_status_code:
            from app.database.models import ReferenceStatus
            status = self.db.query(ReferenceStatus).filter(
                ReferenceStatus.id == company.current_status_code
            ).first()
            if status:
                status_name = status.name

        current_name_fields = self._pick_current_name(company.names_history)

        # Fallback на RawCompanyData только если нет имени
        if not current_name_fields["current_name_ru"]:
            raw_entry = (
                self.db.query(RawCompanyData.data)
                .filter(RawCompanyData.unp == unp)
                .first()
            )
            if raw_entry:
                data = raw_entry.data or {}
                base_info = data.get("base_info") or {}
                common_info = data.get("common_info") or {}
                current_name_fields["current_name_ru"] = (
                    base_info.get("VNAIM") or base_info.get("VFIO")
                    or common_info.get("fullNameRus") or common_info.get("shortNameRus")
                )
                current_name_fields["current_short_name_ru"] = (
                    common_info.get("shortNameRus") or base_info.get("VNAIM")
                )
                current_name_fields["current_name_by"] = (
                    base_info.get("VNAIMBY") or common_info.get("fullNameBel")
                )

        place_location_address = None
        pl = self.db.query(CompanyPlaceLocation).filter(CompanyPlaceLocation.unp == unp).first()
        if pl and pl.address:
            place_location_address = pl.address

        gias_accreditation = None
        if company.gias_accreditation:
            acc = company.gias_accreditation
            gias_accreditation = {
                "state": acc.state,
                "summary": acc.summary,
                "phone": acc.phone,
                "email": acc.email,
                "web_site": acc.web_site,
                "city_name": acc.city_name,
                "placements_address": acc.placements_address,
                "dt_update": acc.dt_update.isoformat() if acc.dt_update else None,
                "dt_from": acc.dt_from.isoformat() if acc.dt_from else None,
                "dt_to": acc.dt_to.isoformat() if acc.dt_to else None,
            }

        gias_locked_suppliers = [
            {
                "state": item.state,
                "name": item.name,
                "location": item.location,
                "reg_number": item.reg_number,
                "add_date": item.add_date.isoformat() if item.add_date else None,
                "del_date": item.del_date.isoformat() if item.del_date else None,
                "base_incl_text": item.base_incl.text if item.base_incl else None,
                "base_excl_text": item.base_excl.text if item.base_excl else None,
                "author_initials": item.author.initials if item.author else None,
            }
            for item in sorted(
                company.gias_locked_suppliers,
                key=lambda row: (row.add_date is not None, row.add_date),
                reverse=True,
            )
        ]

        return {
            "unp": company.unp,
            "current_status_code": company.current_status_code,
            "current_status_name": status_name,
            "registration_date": company.registration_date.isoformat() if company.registration_date else None,
            "liquidation_date": company.liquidation_date.isoformat() if company.liquidation_date else None,
            **current_name_fields,
            "place_location_address": place_location_address,
            "gias_accreditation": gias_accreditation,
            "gias_locked_suppliers": gias_locked_suppliers,
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



