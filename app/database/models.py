"""Database models"""
from sqlalchemy import Column, Integer, String, Date, Boolean, ForeignKey, Text, BigInteger, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import uuid as uuid_pkg


class SystemState(Base):
    """System state for storing sync cursors"""
    __tablename__ = "egr_system_state"
    
    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class RawCompanyData(Base):
    """Buffer for storing raw API responses (ELT pattern)"""
    __tablename__ = "egr_raw_company_data"
    
    unp = Column(BigInteger, primary_key=True, index=True)
    data = Column(JSONB, nullable=False)  # Full JSON response
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # NULL means data is new/updated and needs parsing
    processed_at = Column(DateTime, nullable=True)
    
    # Error text if parsing failed
    last_error = Column(Text, nullable=True)


class GrpRawData(Base):
    """Raw JSON data from GRP API (сырые данные ГРП)"""
    __tablename__ = "grp_raw_data"
    
    unp = Column(BigInteger, primary_key=True, index=True)
    raw_json = Column(JSONB, nullable=False)
    http_status = Column(Integer, nullable=True)
    last_error = Column(Text, nullable=True)
    fetched_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    parsed = Column(Boolean, default=False, index=True)  # Признак парсинга
    parsed_at = Column(DateTime, nullable=True)


class GrpTaxpayerData(Base):
    """GRP (Государственный реестр плательщиков) taxpayer data - parsed structured data"""
    __tablename__ = "grp_taxpayer_data"
    
    unp = Column(BigInteger, primary_key=True, index=True)
    full_name = Column(String, nullable=True)
    short_name = Column(String, nullable=True)
    registration_date = Column(Date, nullable=True)
    
    # Inspectorate info
    inspectorate_code = Column(String, nullable=True)
    inspectorate_name = Column(String, nullable=True)
    
    # Status
    status_code = Column(String, nullable=True)
    status_date = Column(Date, nullable=True)
    
    # Address
    address = Column(Text, nullable=True)
    
    # Metadata
    fetched_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Company(Base):
    """Main company table"""
    __tablename__ = "egr_companies"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    unp = Column(BigInteger, unique=True, nullable=False, index=True)
    current_status_code = Column(Integer)
    registration_date = Column(Date)
    
    # Creation fields
    creation_method_id = Column(Integer, ForeignKey('ref_creation_methods.id'), nullable=True)
    creation_decision_no = Column(String, nullable=True)
    creation_authority_id = Column(Integer, ForeignKey('ref_authorities.id'), nullable=True)
    
    # Current authority
    current_authority_id = Column(Integer, ForeignKey('ref_authorities.id'), nullable=True)
    
    # Entity type (ЮЛ/ИП)
    entity_type_id = Column(Integer, ForeignKey('ref_entity_types.id'), nullable=True)
    
    # Liquidation fields
    liquidation_date = Column(Date, nullable=True)
    liquidation_reason_id = Column(Integer, ForeignKey('ref_liquidation_methods.id'), nullable=True)
    liquidation_decision_no = Column(String, nullable=True)
    liquidation_authority_id = Column(Integer, ForeignKey('ref_authorities.id'), nullable=True)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships to reference tables
    creation_method = relationship("ReferenceCreationMethod", foreign_keys=[creation_method_id])
    creation_authority = relationship("ReferenceAuthority", foreign_keys=[creation_authority_id])
    current_authority = relationship("ReferenceAuthority", foreign_keys=[current_authority_id])
    liquidation_authority = relationship("ReferenceAuthority", foreign_keys=[liquidation_authority_id])
    liquidation_reason = relationship("ReferenceLiquidationMethod", foreign_keys=[liquidation_reason_id])
    entity_type = relationship("ReferenceEntityType", foreign_keys=[entity_type_id])
    
    # Relationships to history tables
    names_history = relationship("CompanyNameHistory", back_populates="company", cascade="all, delete-orphan")
    addresses_history = relationship("CompanyAddressHistory", back_populates="company", cascade="all, delete-orphan")
    ved_history = relationship("CompanyVEDHistory", back_populates="company", cascade="all, delete-orphan")
    contacts_history = relationship("CompanyContactHistory", back_populates="company", cascade="all, delete-orphan")
    sync_history = relationship("SyncHistory", back_populates="company", cascade="all, delete-orphan")
    events = relationship("CompanyEvent", back_populates="company", cascade="all, delete-orphan")


class CompanyNameHistory(Base):
    """Company name history"""
    __tablename__ = "egr_company_names_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey('egr_companies.id', ondelete='CASCADE'), nullable=False)
    full_name_ru = Column(String)
    short_name_ru = Column(String)
    full_name_by = Column(String)
    search_name = Column(String, index=True)  # Нормализованное название для поиска
    valid_from = Column(Date)
    valid_to = Column(Date)
    
    company = relationship("Company", back_populates="names_history")


class CompanyAddressHistory(Base):
    """Company address history"""
    __tablename__ = "egr_company_addresses_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey('egr_companies.id', ondelete='CASCADE'), nullable=False)
    full_address = Column(Text)
    postal_code = Column(Integer)
    region = Column(String)
    district = Column(String)
    valid_from = Column(Date)
    valid_to = Column(Date)
    
    company = relationship("Company", back_populates="addresses_history")


class CompanyVEDHistory(Base):
    """Company VED (activity codes) history"""
    __tablename__ = "egr_company_ved_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey('egr_companies.id', ondelete='CASCADE'), nullable=False)
    ved_code = Column(String)
    ved_name = Column(String)
    valid_from = Column(Date)
    valid_to = Column(Date)
    
    company = relationship("Company", back_populates="ved_history")


class CompanyContactHistory(Base):
    """Company contact information history"""
    __tablename__ = "egr_company_contacts_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey('egr_companies.id', ondelete='CASCADE'), nullable=False)
    email = Column(String, nullable=True)
    website = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    fax = Column(String, nullable=True)
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    
    company = relationship("Company", back_populates="contacts_history")


class SyncHistory(Base):
    """Synchronization history log"""
    __tablename__ = "egr_sync_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey('egr_companies.id', ondelete='CASCADE'), nullable=False)
    sync_type = Column(String(50), nullable=False)
    sync_date = Column(DateTime, nullable=False)
    changes_detected = Column(Boolean)
    status = Column(String(20), nullable=False)
    details = Column(JSONB)
    
    company = relationship("Company", back_populates="sync_history")


class CompanyEvent(Base):
    """Company events history (registration, liquidation, bankruptcy, etc.)"""
    __tablename__ = "egr_company_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey('egr_companies.id', ondelete='CASCADE'), nullable=False)
    
    # Event identification
    event_record_id = Column(Integer, nullable=True)  # NGR04004 - PK записи в ЕГР
    event_type_id = Column(Integer, ForeignKey('ref_events.id'), nullable=True)  # nsi00223
    
    # Event dates
    event_date = Column(Date, nullable=True)  # dfrom - дата головного события
    cancel_date = Column(Date, nullable=True)  # dto - дата отмены события
    document_date = Column(Date, nullable=True)  # ddoc - дата подачи документа
    deadline_date = Column(Date, nullable=True)  # dsrok - срок (для ликвидации)
    suspension_end_date = Column(Date, nullable=True)  # dsrok2 - дата окончания приостановления деятельности ИП
    
    # Document information
    document_number = Column(String, nullable=True)  # vdocn - номер документа
    
    # Authorities
    decision_authority_id = Column(Integer, ForeignKey('ref_authorities.id'), nullable=True)  # nsi00212R
    document_authority_id = Column(Integer, ForeignKey('ref_authorities.id'), nullable=True)  # nsi00212D
    
    # Foundation
    foundation_id = Column(Integer, ForeignKey('ref_foundations.id'), nullable=True)  # nsi00213
    
    # Additional info
    notes = Column(Text, nullable=True)  # vprim - примечание к событию
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    company = relationship("Company", back_populates="events")
    event_type = relationship("ReferenceEvent", foreign_keys=[event_type_id])
    decision_authority = relationship("ReferenceAuthority", foreign_keys=[decision_authority_id])
    document_authority = relationship("ReferenceAuthority", foreign_keys=[document_authority_id])
    foundation = relationship("ReferenceFoundation", foreign_keys=[foundation_id])


class ApiLog(Base):
    """API request logging"""
    __tablename__ = "egr_api_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    request_id = Column(String(100), nullable=False)
    company_unp = Column(BigInteger, nullable=True)
    endpoint = Column(String(200), nullable=False)
    method = Column(String(10), nullable=False)
    response_status = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


# =====================================================
# Reference Tables (Справочники NSI)
# =====================================================

class ReferenceStatus(Base):
    """Справочник статусов компаний - TSI00219"""
    __tablename__ = "ref_statuses"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    system_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReferenceCreationMethod(Base):
    """Справочник способов создания - TSI00208"""
    __tablename__ = "ref_creation_methods"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    system_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReferenceEntityType(Base):
    """Справочник видов объектов (ЮЛ/ИП) - TSI00211"""
    __tablename__ = "ref_entity_types"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    system_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReferenceAuthority(Base):
    """Справочник органов ЕГР - TSI00212"""
    __tablename__ = "ref_authorities"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    system_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReferenceLiquidationMethod(Base):
    """Справочник способов ликвидации - TSI00228"""
    __tablename__ = "ref_liquidation_methods"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    system_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReferenceVED(Base):
    """Справочник видов экономической деятельности - TSI00114"""
    __tablename__ = "ref_ved"
    
    id = Column(Integer, primary_key=True)
    code = Column(String)
    name = Column(String, nullable=False)
    system_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReferenceCountry(Base):
    """Справочник стран мира - TSI00201"""
    __tablename__ = "ref_countries"
    
    id = Column(Integer, primary_key=True)
    code = Column(Integer)
    name = Column(String, nullable=False)
    system_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReferenceSOATO(Base):
    """Справочник СОАТО (территории РБ) - TSI00202"""
    __tablename__ = "ref_soato"
    
    id = Column(Integer, primary_key=True)
    code = Column(BigInteger)
    name = Column(String, nullable=False)
    object_number = Column(Integer)
    system_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReferenceFoundation(Base):
    """Справочник оснований для внесения - TSI00213"""
    __tablename__ = "ref_foundations"
    
    id = Column(Integer, primary_key=True)
    code = Column(Integer)
    name = Column(String, nullable=False)
    system_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReferenceEvent(Base):
    """Справочник событий субъектов - TSI00223"""
    __tablename__ = "ref_events"
    
    id = Column(Integer, primary_key=True)
    code = Column(Integer)
    name = Column(String, nullable=False)
    system_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReferenceStreetType(Base):
    """Справочник типов элементов улично-дорожной сети - TSI00226"""
    __tablename__ = "ref_street_types"
    
    id = Column(Integer, primary_key=True)
    code = Column(Integer)
    name = Column(String, nullable=False)
    system_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReferenceRoomType(Base):
    """Справочник типов помещений - TSI00227"""
    __tablename__ = "ref_room_types"
    
    id = Column(Integer, primary_key=True)
    code = Column(Integer)
    name = Column(String, nullable=False)
    system_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReferenceRoomCategory(Base):
    """Справочник видов помещений - TSI00234"""
    __tablename__ = "ref_room_categories"
    
    id = Column(Integer, primary_key=True)
    code = Column(Integer)
    name = Column(String, nullable=False)
    system_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReferenceSettlementType(Base):
    """Справочник типов населенных пунктов - TSI00239"""
    __tablename__ = "ref_settlement_types"
    
    id = Column(Integer, primary_key=True)
    code = Column(Integer)
    name = Column(String, nullable=False)
    system_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReferenceDocumentType(Base):
    """Справочник видов документов - TSI00206"""
    __tablename__ = "ref_document_types"
    
    id = Column(Integer, primary_key=True)
    code = Column(Integer)
    name = Column(String, nullable=False)
    system_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReferenceCurrency(Base):
    """Справочник валют - TSI00204"""
    __tablename__ = "ref_currencies"
    
    id = Column(Integer, primary_key=True)
    code = Column(Integer)
    name = Column(String, nullable=False)
    system_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReferencePosition(Base):
    """Справочник должностей - TSI00207"""
    __tablename__ = "ref_positions"
    
    id = Column(Integer, primary_key=True)
    code = Column(Integer)
    name = Column(String, nullable=False)
    system_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReferenceOPF(Base):
    """Справочник организационно-правовых форм - TSI00203"""
    __tablename__ = "ref_opf"

    id = Column(Integer, primary_key=True)
    code = Column(Integer)
    name = Column(String, nullable=False)
    system_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class NalogDebtRecord(Base):
    """
    Записи задолженности с портала portal.nalog.gov.by (скрипт Start.py).
    Один срез по дате (slice_date) — множество записей по УНП/ИМНС/датам.
    """
    __tablename__ = "nalog_debt_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    debtor_unp = Column(BigInteger, nullable=False, index=True)
    imns_code = Column(String(10), nullable=False)
    imns_name = Column(String(500), nullable=True)
    debt_date = Column(String(50), nullable=False)   # Дата задолженности (как в источнике)
    repayment_date = Column(String(50), nullable=False)  # Дата погашения задолженности
    slice_date = Column(Date, nullable=False, index=True)  # Дата среза (месяц)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "debtor_unp", "imns_code", "debt_date", "repayment_date", "slice_date",
            name="uq_nalog_debt_unp_imns_dates_slice",
        ),
    )






