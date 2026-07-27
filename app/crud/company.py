"""CRUD operations for companies"""
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, text, func, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.database.models import (
    BankrotCase,
    BankrotCaseDataset,
    Company,
    CompanyNameHistory,
    CompanyAddressHistory,
    CompanyVEDHistory,
    CompanyContactHistory,
    CompanyContact,
    SyncHistory,
    RawCompanyData,
    CompanyPlaceLocation,
    GiasAccreditedCustomer,
    LockedSupplier,
    PVTResidentRecord,
    EAEUSEZResidentRecord,
    TradeRegistryRecord,
    LicenseRecord,
    InspectionPlanRecord,
    BeltppOwnCertificate,
    GiasContract,
)
from datetime import datetime
import logging
from app.utils.search_normalizer import normalize_company_name
from app.services.contact_parser import parse_contacts

logger = logging.getLogger(__name__)

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
        # A successfully parsed EGR card supersedes a minimal GRP/GIAS stub.
        company_data["source"] = "egr"

        # Ensure ref tables have rows for all FK ids (avoids ForeignKeyViolation when update_reference_tables missed some)
        self._ensure_ref_ids_for_company(company_data)
        self.db.flush()
        
        # Снимок старого состояния ДО upsert — для детекции событий подписок.
        old = (
            self.db.query(Company.current_status_code, Company.liquidation_date)
            .filter(Company.unp == unp)
            .first()
        )
        is_new_company = old is None
        old_status = old.current_status_code if old else None
        old_liquidation = old.liquidation_date if old else None

        # Надёжный upsert по UNP без гонок:
        # всегда выполняем INSERT ... ON CONFLICT (unp) DO UPDATE.
        # При обновлении не трогаем поле id, чтобы не ломать внешние ключи.
        # set_ для DO UPDATE: все поля кроме unp/id + принудительно updated_at=now().
        # Core INSERT ... ON CONFLICT не триггерит ORM-овский onupdate=func.now(),
        # поэтому без явного updated_at дата обновления существующих карточек "замерзает".
        update_set = {k: v for k, v in company_data.items() if k not in ("unp", "id")}
        update_set["updated_at"] = func.now()
        stmt = pg_insert(Company).values(**company_data).on_conflict_do_update(
            index_elements=[Company.unp],
            set_=update_set,
        )
        self.db.execute(stmt)
        self.db.flush()
        company = self.get_by_unp(unp)

        # История: методы возвращают список добавленных записей (для детекции событий).
        added_names = self._save_names_history(company, data.get("names", []))
        added_addresses = self._save_addresses_history(company, data.get("addresses", []))
        added_ved = self._save_ved_history(company, data.get("ved", []))
        self._save_contacts_history(company, data.get("contacts", []))

        # Эмиссия событий подписок (в ту же сессию, до commit).
        self._emit_subscription_events(
            unp=unp,
            is_new_company=is_new_company,
            old_status=old_status,
            new_status=company_data.get("current_status_code"),
            old_liquidation=old_liquidation,
            new_liquidation=company_data.get("liquidation_date"),
            added_names=added_names,
            added_addresses=added_addresses,
            added_ved=added_ved,
        )

        try:
            from app.services.search_index import enqueue_company_for_indexing

            enqueue_company_for_indexing(self.db, unp)
        except Exception as search_error:
            # Сбой постановки в поисковую очередь не должен валить запись компании:
            # карточка уже сохранена в БД, переиндексацию подхватит process_search_index_queue.
            logger.warning(f"Failed to enqueue company {unp} for search indexing: {search_error}")

        self.db.commit()
        return company

    def _emit_subscription_events(self, *, unp, is_new_company, old_status, new_status,
                                  old_liquidation, new_liquidation,
                                  added_names, added_addresses, added_ved):
        """Поставить в очередь subscription_events изменения, на которые кто-то подписан."""
        try:
            from app.services.subscription_events import (
                emit_company_event,
                EVENT_NEW_REGISTRATION, EVENT_STATUS_CHANGED, EVENT_LIQUIDATION,
                EVENT_NAME_CHANGED, EVENT_ADDRESS_CHANGED, EVENT_VED_CHANGED,
            )
            if is_new_company:
                # Для новой компании прочие «изменения» — это первичный налив, не события.
                emit_company_event(self.db, unp, EVENT_NEW_REGISTRATION)
                return
            if old_status != new_status:
                emit_company_event(self.db, unp, EVENT_STATUS_CHANGED,
                                   old_value=old_status, new_value=new_status)
            if not old_liquidation and new_liquidation:
                emit_company_event(self.db, unp, EVENT_LIQUIDATION,
                                   new_value=new_liquidation)
            if added_names:
                names = [n.get("full_name_ru") or n.get("short_name_ru") for n in added_names]
                emit_company_event(self.db, unp, EVENT_NAME_CHANGED,
                                   new_value="; ".join(x for x in names if x))
            if added_addresses:
                addrs = [a.get("full_address") for a in added_addresses]
                emit_company_event(self.db, unp, EVENT_ADDRESS_CHANGED,
                                   new_value="; ".join(x for x in addrs if x))
            if added_ved:
                veds = [v.get("ved_code") for v in added_ved]
                emit_company_event(self.db, unp, EVENT_VED_CHANGED,
                                   new_value="; ".join(x for x in veds if x))
        except Exception as e:
            # Эмиссия событий не должна валить сохранение карточки.
            logger.warning(f"subscription event emit failed for {unp}: {e}")

    def _save_names_history(self, company: Company, names: List[Dict]):
        """Save names history with automatic search_name generation"""
        # Одним запросом тянем существующие ключи (company_id, full_name_ru, valid_from),
        # чтобы не делать SELECT на каждую запись (N+1).
        existing_keys = {
            (r.full_name_ru, r.valid_from)
            for r in self.db.query(
                CompanyNameHistory.full_name_ru, CompanyNameHistory.valid_from
            ).filter(CompanyNameHistory.company_id == company.id).all()
        }
        added: List[Dict] = []
        for name_data in names:
            key = (name_data.get("full_name_ru"), name_data.get("valid_from"))
            if key in existing_keys:
                continue
            existing_keys.add(key)  # дедуп и внутри входящего списка

            # Автоматически генерируем search_name для умного поиска
            full_name = name_data.get("full_name_ru") or name_data.get("short_name_ru") or name_data.get("full_name_by")
            search_name = normalize_company_name(full_name) if full_name else None

            name_entry = CompanyNameHistory(
                company_id=company.id,
                search_name=search_name,  # Умный поиск
                **name_data
            )
            self.db.add(name_entry)
            added.append(name_data)
        return added

    def _save_addresses_history(self, company: Company, addresses: List[Dict]):
        """Save addresses history"""
        existing_keys = {
            (r.full_address, r.valid_from)
            for r in self.db.query(
                CompanyAddressHistory.full_address, CompanyAddressHistory.valid_from
            ).filter(CompanyAddressHistory.company_id == company.id).all()
        }
        added: List[Dict] = []
        for addr_data in addresses:
            key = (addr_data.get("full_address"), addr_data.get("valid_from"))
            if key in existing_keys:
                continue
            existing_keys.add(key)
            addr_entry = CompanyAddressHistory(
                company_id=company.id,
                **addr_data
            )
            self.db.add(addr_entry)
            added.append(addr_data)
        return added

    def _save_ved_history(self, company: Company, ved_list: List[Dict]):
        """Save VED history"""
        existing_keys = {
            (r.ved_code, r.valid_from)
            for r in self.db.query(
                CompanyVEDHistory.ved_code, CompanyVEDHistory.valid_from
            ).filter(CompanyVEDHistory.company_id == company.id).all()
        }
        added: List[Dict] = []
        for ved_data in ved_list:
            key = (ved_data.get("ved_code"), ved_data.get("valid_from"))
            if key in existing_keys:
                continue
            existing_keys.add(key)
            ved_entry = CompanyVEDHistory(
                company_id=company.id,
                **ved_data
            )
            self.db.add(ved_entry)
            added.append(ved_data)
        return added

    def _save_contacts_history(self, company: Company, contacts: List[Dict]):
        """Save contacts history"""
        existing_keys = {
            (r.email, r.valid_from)
            for r in self.db.query(
                CompanyContactHistory.email, CompanyContactHistory.valid_from
            ).filter(CompanyContactHistory.company_id == company.id).all()
        }
        for contact_data in contacts:
            key = (contact_data.get("email"), contact_data.get("valid_from"))
            if key in existing_keys:
                continue
            existing_keys.add(key)
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
        place_location_lat = None
        place_location_lon = None
        pl = self.db.query(CompanyPlaceLocation).filter(CompanyPlaceLocation.unp == unp).first()
        if pl:
            if pl.address:
                place_location_address = pl.address
            place_location_lat = pl.lat
            place_location_lon = pl.lon

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

        gias_contracts = [
            {
                "contract_id": str(item.contract_id),
                "role": (
                    "customer"
                    if item.customer_company_id == company.id
                    else "provider"
                ),
                "counterparty_unp": (
                    item.provider_unp
                    if item.customer_company_id == company.id
                    else item.customer_unp
                ),
                "counterparty_name": (
                    item.provider_name
                    if item.customer_company_id == company.id
                    else item.customer_name
                ),
                "registration_number": item.registration_number,
                "contract_number": item.contract_number,
                "title": item.title,
                "state": item.state,
                "price": float(item.price) if item.price is not None else None,
                "currency_code": item.currency_code,
                "contract_date": (
                    item.contract_date.isoformat()
                    if item.contract_date
                    else None
                ),
                "source_updated_at": (
                    item.source_updated_at.isoformat()
                    if item.source_updated_at
                    else None
                ),
                "detail_status": item.detail_status,
            }
            for item in (
                self.db.query(GiasContract)
                .filter(
                    or_(
                        GiasContract.customer_company_id == company.id,
                        GiasContract.provider_company_id == company.id,
                    )
                )
                .order_by(GiasContract.source_updated_at.desc().nullslast())
                .limit(100)
                .all()
            )
        ]

        pvt_resident = None
        pvt = (
            self.db.query(PVTResidentRecord)
            .filter(PVTResidentRecord.unp == unp)
            .order_by(PVTResidentRecord.last_seen_at.desc())
            .first()
        )
        if pvt:
            pvt_raw = pvt.raw_json or {}
            pvt_resident = {
                "name": pvt.name,
                "profile_url": pvt.profile_url,
                "description": pvt.description or pvt_raw.get("list_description"),
                "source_url": pvt.source_url,
                "city": pvt_raw.get("city"),
                "legal_address": pvt_raw.get("legal_address"),
                "phone": pvt_raw.get("phone"),
                "website": pvt_raw.get("website"),
                "activity_directions": pvt_raw.get("activity_directions") or [],
                "list_description": pvt_raw.get("list_description"),
                "last_seen_at": pvt.last_seen_at.isoformat() if pvt.last_seen_at else None,
            }

        trade_registry_rows = (
            self.db.query(TradeRegistryRecord)
            .filter(TradeRegistryRecord.unp == unp)
            .order_by(
                TradeRegistryRecord.object_type.asc().nullsfirst(),
                TradeRegistryRecord.object_name.asc().nullsfirst(),
                TradeRegistryRecord.registration_number.asc(),
            )
            .all()
        )

        trade_registry_records = [
            {
                "registration_number": item.registration_number,
                "legal_name": item.legal_name,
                "legal_address": item.legal_address,
                "object_type": item.object_type,
                "object_name": item.object_name,
                "internet_shop_domain": item.internet_shop_domain,
                "trade_network_name": item.trade_network_name,
                "object_region": item.object_region,
                "object_district": item.object_district,
                "object_locality": item.object_locality,
                "object_street": item.object_street,
                "object_building": item.object_building,
                "object_office": item.object_office,
                "object_contacts": item.object_contacts,
                "object_contacts_parsed": parse_contacts(item.object_contacts),
                "format_type": item.format_type,
                "location_type": item.location_type,
                "assortment_type": item.assortment_type,
                "trade_object_type": item.trade_object_type,
                "trade_area": item.trade_area,
                "retail_trade": item.retail_trade,
                "wholesale_trade": item.wholesale_trade,
                "goods_groups": item.goods_groups,
                "inclusion_date": item.inclusion_date.isoformat() if item.inclusion_date else None,
                "source_date": item.source_date.isoformat() if item.source_date else None,
                "source_file": item.source_file,
                "last_seen_at": item.last_seen_at.isoformat() if item.last_seen_at else None,
            }
            for item in trade_registry_rows
        ]

        sez_rows = (
            self.db.query(EAEUSEZResidentRecord)
            .filter(EAEUSEZResidentRecord.unp == unp)
            .order_by(
                EAEUSEZResidentRecord.sez_name.asc().nullsfirst(),
                EAEUSEZResidentRecord.item_id.asc(),
            )
            .all()
        )
        eaeu_sez_resident_records = [
            {
                "item_id": item.item_id,
                "country": item.country,
                "full_name": item.full_name,
                "short_name": item.short_name,
                "legal_address": item.legal_address,
                "firm_name": item.firm_name,
                "registration_agency": item.registration_agency,
                "sez_name": item.sez_name,
                "project_name": item.project_name,
                "registry_entry_date": item.registry_entry_date,
                "certificate": item.certificate,
                "source_url": item.source_url,
                "last_seen_at": item.last_seen_at.isoformat() if item.last_seen_at else None,
            }
            for item in sez_rows
        ]

        license_rows = (
            self.db.query(LicenseRecord)
            .filter(LicenseRecord.holder_unp == unp)
            .order_by(
                LicenseRecord.activity_is_active.desc().nullslast(),
                LicenseRecord.last_seen_at.desc().nullslast(),
                LicenseRecord.license_id.desc(),
            )
            .all()
        )
        license_records = [
            {
                "license_id": item.license_id,
                "generated_number": item.generated_number,
                "holder_name": item.holder_name,
                "activity_type_name": item.activity_type_name,
                "activity_date_start": item.activity_date_start.isoformat() if item.activity_date_start else None,
                "activity_date_end": item.activity_date_end.isoformat() if item.activity_date_end else None,
                "activity_is_active": item.activity_is_active,
                "last_seen_at": item.last_seen_at.isoformat() if item.last_seen_at else None,
            }
            for item in license_rows
        ]

        inspection_plan_rows = (
            self.db.query(InspectionPlanRecord)
            .filter(InspectionPlanRecord.subject_unp == unp)
            .order_by(
                InspectionPlanRecord.plan_year.desc().nullslast(),
                InspectionPlanRecord.plan_half.desc().nullslast(),
                InspectionPlanRecord.start_month_no.asc().nullslast(),
                InspectionPlanRecord.plan_item_no.asc().nullslast(),
                InspectionPlanRecord.controller_authority.asc().nullsfirst(),
            )
            .all()
        )
        inspection_plan_records = [
            {
                "plan_period": item.plan_period,
                "plan_year": item.plan_year,
                "plan_half": item.plan_half,
                "source_region": item.source_region,
                "plan_title": item.plan_title,
                "plan_item_no": item.plan_item_no,
                "approving_authority": item.approving_authority,
                "controller_unp": item.controller_unp,
                "controller_authority": item.controller_authority,
                "executor_phone": item.executor_phone,
                "start_month": item.start_month,
                "start_month_no": item.start_month_no,
                "source_file": item.source_file,
                "last_seen_at": item.last_seen_at.isoformat() if item.last_seen_at else None,
            }
            for item in inspection_plan_rows
        ]

        belltpp_own_certificate_rows = (
            self.db.query(BeltppOwnCertificate)
            .filter(BeltppOwnCertificate.holder_unp == unp)
            .order_by(
                BeltppOwnCertificate.valid_until.desc().nullslast(),
                BeltppOwnCertificate.issue_date.desc().nullslast(),
                BeltppOwnCertificate.cert_number.asc(),
            )
            .all()
        )
        belltpp_own_certificates = [
            {
                "holder_name": item.holder_name,
                "cert_number": item.cert_number,
                "blank_number": item.blank_number,
                "issue_date": item.issue_date.isoformat() if item.issue_date else None,
                "valid_until": item.valid_until.isoformat() if item.valid_until else None,
                "verify_url": item.verify_url,
                "products": item.products or [],
                "last_seen_at": item.last_seen_at.isoformat() if item.last_seen_at else None,
            }
            for item in belltpp_own_certificate_rows
        ]

        # Дела о банкротстве — мягкая связь по УНП
        bankrot_rows = (
            self.db.query(BankrotCase)
            .filter(BankrotCase.debtor_unp == unp)
            .order_by(BankrotCase.start_date.desc().nullslast())
            .all()
        )
        bankrot_cases = [
            {
                "case_id":        row.case_id,
                "number":         row.number,
                "start_date":     row.start_date.isoformat() if row.start_date else None,
                "end_date":       row.end_date.isoformat()   if row.end_date   else None,
                "status":         row.status,
                "procedure_type": row.procedure_type,
                "court":          row.court,
                "judge":          row.judge,
                "manager_name":   row.manager_name,
                "updated_at":     row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in bankrot_rows
        ]

        # Агрегированные контакты: дедуп по (type, value_norm), источники — списком.
        contact_rows = (
            self.db.query(CompanyContact)
            .filter(CompanyContact.company_id == company.id)
            .order_by(CompanyContact.contact_type, CompanyContact.value)
            .all()
        )
        _agg: Dict = {}
        for cc in contact_rows:
            entry = _agg.get((cc.contact_type, cc.value_norm))
            if entry is None:
                _agg[(cc.contact_type, cc.value_norm)] = {
                    "contact_type": cc.contact_type,
                    "value": cc.value,
                    "full_name": cc.full_name,
                    "position": cc.position,
                    "sources": [cc.source],
                }
            else:
                if cc.source not in entry["sources"]:
                    entry["sources"].append(cc.source)
                if not entry["full_name"] and cc.full_name:
                    entry["full_name"] = cc.full_name
                if not entry["position"] and cc.position:
                    entry["position"] = cc.position
        contacts_aggregated = list(_agg.values())

        return {
            "unp": company.unp,
            "entity_type_id": company.entity_type_id,
            "current_status_code": company.current_status_code,
            "current_status_name": status_name,
            "registration_date": company.registration_date.isoformat() if company.registration_date else None,
            "liquidation_date": company.liquidation_date.isoformat() if company.liquidation_date else None,
            **current_name_fields,
            "place_location_address": place_location_address,
            "latitude": place_location_lat,
            "longitude": place_location_lon,
            "gias_accreditation": gias_accreditation,
            "gias_locked_suppliers": gias_locked_suppliers,
            "gias_contracts": gias_contracts,
            "pvt_resident": pvt_resident,
            "trade_registry_records": trade_registry_records,
            "contacts_aggregated": contacts_aggregated,
            "eaeu_sez_resident_records": eaeu_sez_resident_records,
            "license_records": license_records,
            "inspection_plan_records": inspection_plan_records,
            "belltpp_own_certificates": belltpp_own_certificates,
            "bankrot_cases": bankrot_cases,
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

    def get_bankrot_dossier(self, unp: int) -> Dict[str, Any]:
        """Полные локальные данные bankrot.gov.by по УНП без внешних запросов."""
        cases = (
            self.db.query(BankrotCase)
            .filter(BankrotCase.debtor_unp == unp)
            .order_by(BankrotCase.start_date.desc().nullslast())
            .all()
        )
        case_ids = [row.case_id for row in cases]
        datasets_by_case: Dict[int, List[Dict[str, Any]]] = {
            case_id: [] for case_id in case_ids
        }
        if case_ids:
            dataset_rows = (
                self.db.query(BankrotCaseDataset)
                .filter(BankrotCaseDataset.case_id.in_(case_ids))
                .order_by(
                    BankrotCaseDataset.case_id,
                    BankrotCaseDataset.dataset_type,
                )
                .all()
            )
            for dataset in dataset_rows:
                datasets_by_case[dataset.case_id].append(
                    {
                        "dataset_type": dataset.dataset_type,
                        "endpoint": dataset.endpoint,
                        "http_method": dataset.http_method,
                        "payload": dataset.payload,
                        "fetch_error": dataset.fetch_error,
                        "fetched_at": (
                            dataset.fetched_at.isoformat()
                            if dataset.fetched_at
                            else None
                        ),
                        "updated_at": dataset.updated_at.isoformat(),
                    }
                )

        return {
            "unp": unp,
            "cases": [
                {
                    "case_id": row.case_id,
                    "debtor_unp": row.debtor_unp,
                    "number": row.number,
                    "start_date": row.start_date.isoformat() if row.start_date else None,
                    "end_date": row.end_date.isoformat() if row.end_date else None,
                    "status": row.status,
                    "procedure_type": row.procedure_type,
                    "court": row.court,
                    "judge": row.judge,
                    "manager_id": row.manager_id,
                    "manager_name": row.manager_name,
                    "last_judgment_id": row.last_judgment_id,
                    "list_data": row.list_data,
                    "detail_data": row.detail_data,
                    "judgements_group": row.judgements_group,
                    "fetch_error": row.fetch_error,
                    "updated_at": row.updated_at.isoformat(),
                    "datasets": datasets_by_case[row.case_id],
                }
                for row in cases
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
