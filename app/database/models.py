"""Database models"""
from sqlalchemy import Column, Integer, String, Date, Boolean, ForeignKey, Text, BigInteger, DateTime, Float, UniqueConstraint, false
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


class SearchIndexQueue(Base):
    """Outbox queue for keeping Elasticsearch in sync with PostgreSQL."""
    __tablename__ = "search_index_queue"

    unp = Column(BigInteger, primary_key=True)
    operation = Column(String(20), nullable=False, default="index")
    status = Column(String(20), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    enqueued_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    indexed_at = Column(DateTime, nullable=True)


class RawCompanyData(Base):
    """
    Buffer for storing raw API responses (ELT pattern).
    Для обратной совместимости:
    - основное поле `data` содержит полный JSON (base_info + addresses + ved + names)
    - при наличии отдельных колонок по эндпоинтам (base_info/addresses/ved/names)
      метод `get_data()` собирает сводную структуру.
    """
    __tablename__ = "egr_raw_company_data"
    
    unp = Column(BigInteger, primary_key=True, index=True)
    # Сводная колонка (для парсинга и кэша)
    data = Column(JSONB, nullable=True)
    
    # Отдельные колонки по эндпоинтам (могут отсутствовать в старой БД, но
    # для них есть alembic‑миграция e5f6g7h8i9_raw_per_endpoint_columns.py)
    base_info = Column(JSONB, nullable=True)
    base_info_fetched_at = Column(DateTime, nullable=True)
    addresses = Column(JSONB, nullable=True)
    addresses_fetched_at = Column(DateTime, nullable=True)
    ved = Column(JSONB, nullable=True)
    ved_fetched_at = Column(DateTime, nullable=True)
    names = Column(JSONB, nullable=True)
    names_fetched_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # NULL means data is new/updated and needs parsing
    processed_at = Column(DateTime, nullable=True)
    
    # Error text if parsing failed
    last_error = Column(Text, nullable=True)
    # Самозалечивающийся ретрай: счётчик попыток + время следующей попытки (backoff).
    error_attempts = Column(Integer, nullable=False, server_default="0")
    next_retry_at = Column(DateTime, nullable=True, index=True)

    def get_data(self):
        """
        Сводные данные для парсинга:
        - если заполнено поле data — используем его;
        - иначе собираем из base_info / addresses / ved / names (если колонки есть).
        """
        if self.data is not None:
            return self.data
        # Если отдельных колонок нет или все пустые — вернуть None
        if (
            not hasattr(self, "base_info")
            or (self.base_info is None and self.addresses is None and self.ved is None and self.names is None)
        ):
            return None
        return {
            "base_info": self.base_info or {},
            "addresses": self.addresses if self.addresses is not None else [],
            "ved": self.ved if self.ved is not None else [],
            "names": self.names if self.names is not None else [],
        }


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
    # Происхождение записи: 'egr' (госрегистрация) | 'grp' (найдено через ГРП —
    # госорганы/бюджетные, которых в ЕГР нет). Центральный реестр = все УНП.
    source = Column(String(8), nullable=False, server_default="egr", index=True)
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
    gias_accreditation = relationship("GiasAccreditedCustomer", back_populates="company", uselist=False)
    gias_locked_suppliers = relationship("LockedSupplier", back_populates="company")
    trade_registry_records = relationship("TradeRegistryRecord", back_populates="company")
    pvt_resident = relationship("PVTResidentRecord", back_populates="company", uselist=False)
    eaeu_sez_resident_records = relationship("EAEUSEZResidentRecord", back_populates="company")
    license_records = relationship("LicenseRecord", back_populates="company")
    inspection_plan_records = relationship("InspectionPlanRecord", back_populates="company")
    belltpp_own_certificates = relationship("BeltppOwnCertificate", back_populates="company")


class TradeRegistryRecord(Base):
    """Rows from the Belarus trade registry, linked only to existing EGR companies."""
    __tablename__ = "trade_registry_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("egr_companies.id", ondelete="CASCADE"), nullable=False, index=True)
    unp = Column(BigInteger, nullable=False, index=True)

    legal_name = Column(Text, nullable=True)
    legal_address = Column(Text, nullable=True)
    object_type = Column(Text, nullable=True)
    object_name = Column(Text, nullable=True)
    internet_shop_domain = Column(Text, nullable=True)
    trade_network_name = Column(Text, nullable=True)

    object_region = Column(Text, nullable=True)
    object_district = Column(Text, nullable=True)
    object_locality = Column(Text, nullable=True)
    object_street = Column(Text, nullable=True)
    object_building = Column(Text, nullable=True)
    object_office = Column(Text, nullable=True)
    object_contacts = Column(Text, nullable=True)

    format_type = Column(Text, nullable=True)
    location_type = Column(Text, nullable=True)
    assortment_type = Column(Text, nullable=True)
    is_firm = Column(String(32), nullable=True)
    trade_object_type = Column(Text, nullable=True)
    trade_area = Column(String(64), nullable=True)

    retail_trade = Column(String(32), nullable=True)
    wholesale_trade = Column(String(32), nullable=True)
    retail_without_object_form = Column(Text, nullable=True)
    wholesale_without_object = Column(String(32), nullable=True)
    goods_classes = Column(Text, nullable=True)
    goods_groups = Column(Text, nullable=True)
    goods_subgroups = Column(Text, nullable=True)

    catering_format_type = Column(Text, nullable=True)
    seats_count = Column(Integer, nullable=True)
    public_seats_count = Column(Integer, nullable=True)
    shopping_center_specializations = Column(Text, nullable=True)
    shopping_center_trade_objects_count = Column(Integer, nullable=True)
    shopping_center_catering_objects_count = Column(Integer, nullable=True)
    shopping_center_trade_area = Column(String(64), nullable=True)
    market_type = Column(Text, nullable=True)
    market_specialization = Column(Text, nullable=True)
    market_places_count = Column(Integer, nullable=True)
    market_trade_objects_count = Column(Integer, nullable=True)

    registration_number = Column(String(64), nullable=False, index=True)
    inclusion_date = Column(Date, nullable=True)
    source_date = Column(Date, nullable=True, index=True)
    source_file = Column(Text, nullable=True)
    raw_json = Column(JSONB, nullable=False)
    sync_hash = Column(String(64), nullable=False)

    first_seen_at = Column(DateTime, nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("unp", "registration_number", name="uq_trade_registry_records_unp_registration_number"),
    )

    company = relationship("Company", back_populates="trade_registry_records")


class InspectionPlanRecord(Base):
    """Rows from Belarus scheduled inspection plans."""
    __tablename__ = "inspection_plan_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("egr_companies.id", ondelete="SET NULL"), nullable=True, index=True)
    subject_unp = Column(BigInteger, nullable=False, index=True)
    subject_name = Column(Text, nullable=False)

    plan_period = Column(String(16), nullable=False, index=True)
    plan_year = Column(Integer, nullable=True, index=True)
    plan_half = Column(Integer, nullable=True, index=True)
    source_region = Column(Text, nullable=False, index=True)
    plan_title = Column(Text, nullable=True)
    plan_item_no = Column(Integer, nullable=True, index=True)

    approving_authority = Column(Text, nullable=True)
    controller_unp = Column(BigInteger, nullable=True, index=True)
    controller_authority = Column(Text, nullable=True)
    executor_phone = Column(Text, nullable=True)
    start_month = Column(String(32), nullable=True, index=True)
    start_month_no = Column(Integer, nullable=True, index=True)

    source_file = Column(Text, nullable=False)
    source_sheet = Column(Text, nullable=False)
    source_row_no = Column(Integer, nullable=False)
    raw_json = Column(JSONB, nullable=False)
    sync_key = Column(String(64), nullable=False)
    sync_hash = Column(String(64), nullable=False)

    first_seen_at = Column(DateTime, nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("sync_key", name="uq_inspection_plan_records_sync_key"),
    )

    company = relationship("Company", back_populates="inspection_plan_records")


class BeltppOwnCertificate(Base):
    """BelTPP certificates for products, works, or services of own production."""
    __tablename__ = "belltpp_own_certificates"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("egr_companies.id", ondelete="SET NULL"), nullable=True, index=True)
    holder_unp = Column(BigInteger, nullable=False, index=True)
    holder_name = Column(Text, nullable=False)

    cert_number = Column(String(64), nullable=False, index=True)
    blank_number = Column(String(64), nullable=True, index=True)
    issue_date = Column(Date, nullable=True, index=True)
    valid_until = Column(Date, nullable=True, index=True)
    verify_url = Column(Text, nullable=True)
    source_url = Column(Text, nullable=False)
    source_page = Column(Integer, nullable=False)
    source_position = Column(Integer, nullable=True)
    source_id = Column(BigInteger, nullable=True, index=True)
    products = Column(JSONB, nullable=False, default=list)
    raw_json = Column(JSONB, nullable=False)
    sync_key = Column(String(64), nullable=False)
    sync_hash = Column(String(64), nullable=False)

    first_seen_at = Column(DateTime, nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("sync_key", name="uq_belltpp_own_certificates_sync_key"),
    )

    company = relationship("Company", back_populates="belltpp_own_certificates")


class TradeRegistryImportRun(Base):
    """Admin-uploaded trade registry CSV import run."""
    __tablename__ = "trade_registry_import_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    status = Column(String(32), nullable=False, default="queued", index=True)
    original_filename = Column(Text, nullable=False)
    stored_path = Column(Text, nullable=False)
    source_date = Column(Date, nullable=True, index=True)
    stats_json = Column(JSONB, nullable=False, default=dict)
    error = Column(Text, nullable=True)
    celery_task_id = Column(String(255), nullable=True)
    created_by = Column(String(255), nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    staged_rows = relationship("TradeRegistryImportStage", back_populates="run", cascade="all, delete-orphan")


class TradeRegistryImportStage(Base):
    """Parsed rows staged before replacing live trade registry rows."""
    __tablename__ = "trade_registry_import_stage"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(UUID(as_uuid=True), ForeignKey("trade_registry_import_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    unp = Column(BigInteger, nullable=False, index=True)
    registration_number = Column(String(64), nullable=False)
    company_id = Column(UUID(as_uuid=True), ForeignKey("egr_companies.id", ondelete="CASCADE"), nullable=False, index=True)
    sync_hash = Column(String(64), nullable=False)
    payload_json = Column(JSONB, nullable=False)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("run_id", "unp", "registration_number", name="uq_trade_registry_import_stage_run_unp_reg"),
    )

    run = relationship("TradeRegistryImportRun", back_populates="staged_rows")
    company = relationship("Company")


class PVTResidentRecord(Base):
    """Hi-Tech Park resident record parsed from park.by and linked to an EGR company."""
    __tablename__ = "pvt_resident_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("egr_companies.id", ondelete="CASCADE"), nullable=False, index=True)
    unp = Column(BigInteger, nullable=False, unique=True, index=True)
    name = Column(Text, nullable=True)
    profile_url = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    raw_json = Column(JSONB, nullable=False)

    first_seen_at = Column(DateTime, nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    company = relationship("Company", back_populates="pvt_resident")


class EAEUSEZResidentRecord(Base):
    """EAEU SEZ resident registry row linked to an EGR company by UNP."""
    __tablename__ = "eaeu_sez_resident_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    item_id = Column(BigInteger, nullable=False, unique=True, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("egr_companies.id", ondelete="CASCADE"), nullable=False, index=True)
    unp = Column(BigInteger, nullable=False, index=True)

    country = Column(String(255), nullable=False, index=True)
    full_name = Column(Text, nullable=True)
    short_name = Column(Text, nullable=True)
    legal_address = Column(Text, nullable=True)
    firm_name = Column(Text, nullable=True)
    registration_agency = Column(Text, nullable=True)
    sez_name = Column(Text, nullable=True)
    project_name = Column(Text, nullable=True)
    registry_entry_date = Column(Text, nullable=True)
    certificate = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    raw_json = Column(JSONB, nullable=False)

    first_seen_at = Column(DateTime, nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    company = relationship("Company", back_populates="eaeu_sez_resident_records")


class LicenseRecord(Base):
    """License registry row from license.gov.by linked to an EGR company by UNP."""
    __tablename__ = "license_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    license_id = Column(BigInteger, nullable=False, unique=True, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("egr_companies.id", ondelete="CASCADE"), nullable=True, index=True)
    holder_unp = Column(BigInteger, nullable=True, index=True)
    holder_name = Column(Text, nullable=True)
    generated_number = Column(String(64), nullable=True, index=True)

    activity_type_id = Column(BigInteger, nullable=True, index=True)
    activity_type_code = Column(String(64), nullable=True)
    activity_type_name = Column(Text, nullable=True, index=True)
    activity_date_start = Column(DateTime, nullable=True)
    activity_date_end = Column(DateTime, nullable=True)
    activity_is_active = Column(Boolean, nullable=True, index=True)

    raw_json = Column(JSONB, nullable=False)
    sync_hash = Column(String(64), nullable=False)
    first_seen_at = Column(DateTime, nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    company = relationship("Company", back_populates="license_records")


class LicenseSyncRun(Base):
    """Synchronization log for license.gov.by registry imports."""
    __tablename__ = "license_sync_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    status = Column(String(32), nullable=False, default="running", index=True)
    started_at = Column(DateTime, nullable=False, server_default=func.now())
    finished_at = Column(DateTime, nullable=True)
    total_records = Column(Integer, nullable=False, default=0)
    processed_records = Column(Integer, nullable=False, default=0)
    created_count = Column(Integer, nullable=False, default=0)
    updated_count = Column(Integer, nullable=False, default=0)
    unchanged_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    last_page = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    stats_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class CompanyPlaceLocation(Base):
    """
    placeLocation из Mobile API: https://egr.gov.by/egrmobile/api/v1/extracts/placeLocation?pan={unp}
    Храним отдельно от egr_raw_company_data, чтобы не перетирать большой JSON и обновлять независимо.
    """
    __tablename__ = "egr_company_place_locations"

    unp = Column(BigInteger, primary_key=True, index=True)
    raw_json = Column(JSONB, nullable=True)
    address = Column(Text, nullable=True)  # “человекочитаемый” адрес (если удаётся извлечь)

    # Координаты адреса. Геокодинг через OSM/Nominatim (хранение разрешено лицензией),
    # НЕ через Яндекс. geocoded_at — отметка последней попытки (в т.ч. неудачной),
    # чтобы не геокодить один и тот же адрес каждый прогон.
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    geocoded_at = Column(DateTime, nullable=True)

    fetched_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CompanyNameHistory(Base):
    """Company name history"""
    __tablename__ = "egr_company_names_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey('egr_companies.id', ondelete='CASCADE'), nullable=False, index=True)
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
    company_id = Column(UUID(as_uuid=True), ForeignKey('egr_companies.id', ondelete='CASCADE'), nullable=False, index=True)
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
    company_id = Column(UUID(as_uuid=True), ForeignKey('egr_companies.id', ondelete='CASCADE'), nullable=False, index=True)
    ved_code = Column(String)
    ved_name = Column(String)
    valid_from = Column(Date)
    valid_to = Column(Date)
    
    company = relationship("Company", back_populates="ved_history")


class CompanyContactHistory(Base):
    """Company contact information history"""
    __tablename__ = "egr_company_contacts_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey('egr_companies.id', ondelete='CASCADE'), nullable=False, index=True)
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
    company_id = Column(UUID(as_uuid=True), ForeignKey('egr_companies.id', ondelete='CASCADE'), nullable=False, index=True)
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
# Подписки пользователей на события компаний
# =====================================================

class User(Base):
    """Аккаунт подписчика (вход через сайт; telegram_id — для будущей привязки бота)."""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    email = Column(String(255), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=True)
    telegram_id = Column(BigInteger, unique=True, nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    # Заполнится, когда появится SMTP/верификация email (сейчас не используется).
    email_verified_at = Column(DateTime, nullable=True)
    # Webhook: «адрес клиента» для push-доставки событий + секрет для подписи (HMAC).
    webhook_url = Column(Text, nullable=True)
    webhook_secret = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    subscriptions = relationship("CompanySubscription", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")


class ApiKey(Base):
    """API-ключ аккаунта для программного доступа (подписки по API)."""
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    key_hash = Column(String(64), unique=True, nullable=False, index=True)  # sha256(raw_key)
    label = Column(String(255), nullable=True)
    revoked = Column(Boolean, nullable=False, server_default=false())
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="api_keys")


class CompanySubscription(Base):
    """Подписка пользователя на изменения конкретной компании (по UNP)."""
    __tablename__ = "company_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    unp = Column(BigInteger, nullable=False, index=True)
    # Список интересующих типов событий; пустой список = все типы.
    event_types = Column(JSONB, nullable=False, server_default="[]")
    source = Column(String(16), nullable=False, server_default="web")  # web | api
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="subscriptions")

    __table_args__ = (
        UniqueConstraint("user_id", "unp", name="uq_company_subscriptions_user_unp"),
    )


class SubscriptionEvent(Base):
    """
    Очередь сработавших событий по подпискам.
    Пишется при обработке данных, когда у компании произошло изменение,
    на которое кто-то подписан. processed_at — задел под доставку/пулинг (позже).
    """
    __tablename__ = "subscription_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    unp = Column(BigInteger, nullable=False, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    old_value = Column(Text, nullable=True)   # было
    new_value = Column(Text, nullable=True)   # стало
    occurred_at = Column(DateTime, nullable=False, server_default=func.now())  # когда событие возникло
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    # Когда обработано (доставлено). NULL = ещё не обработано;
    # можно сбросить в NULL, чтобы обработать заново.
    processed_at = Column(DateTime, nullable=True, index=True)
    # Webhook-доставка: счётчик попыток и последняя ошибка (для ретраев/дед-леттера).
    delivery_attempts = Column(Integer, nullable=False, server_default="0")
    last_delivery_error = Column(Text, nullable=True)


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
    Записи задолженности с портала portal.nalog.gov.by (legacy wrapper Start.py).
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
            "debtor_unp",
            "imns_code",
            "debt_date",
            "repayment_date",
            "slice_date",
            name="uq_nalog_debt_unp_imns_dates_slice",
        ),
    )


class GiasSyncRun(Base):
    """GIAS directory synchronization runs."""
    __tablename__ = "gias_sync_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    registry_name = Column(String(64), nullable=False, index=True)
    status = Column(String(20), nullable=False, index=True)
    started_at = Column(DateTime, nullable=False, server_default=func.now())
    finished_at = Column(DateTime, nullable=True)
    records_fetched = Column(Integer, nullable=False, default=0)
    created_count = Column(Integer, nullable=False, default=0)
    updated_count = Column(Integer, nullable=False, default=0)
    unchanged_count = Column(Integer, nullable=False, default=0)
    history_created_count = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class GiasAccreditedCustomer(Base):
    """Current state of GIAS accredited customers registry."""
    __tablename__ = "gias_accredited_customers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("egr_companies.id", ondelete="CASCADE"), nullable=True, index=True, unique=True)
    unp = Column(String(20), nullable=False, unique=True, index=True)
    name = Column(Text, nullable=False)
    uid_customer = Column(String(255), nullable=True)
    customer_id = Column(String(255), nullable=True)
    summary = Column(Text, nullable=True)
    state = Column(String(50), nullable=True, index=True)
    dt_update = Column(DateTime, nullable=True)
    dt_from = Column(DateTime, nullable=True)
    dt_to = Column(DateTime, nullable=True)
    is_customer = Column(Boolean, nullable=True)
    is_organizator = Column(Boolean, nullable=True)
    phone = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True)
    web_site = Column(String(255), nullable=True)
    region = Column(Integer, nullable=True)
    city_name = Column(String(255), nullable=True)
    placements_address = Column(Text, nullable=True)
    placements_country = Column(String(10), nullable=True)
    placements_post_index = Column(String(20), nullable=True)
    placements_city = Column(String(255), nullable=True)
    placements_address_detail = Column(Text, nullable=True)
    okogu_name = Column(String(255), nullable=True)
    okogu_code = Column(Integer, nullable=True)
    raw_json = Column(JSONB, nullable=True)
    sync_hash = Column(String(64), nullable=True)
    first_seen_at = Column(DateTime, nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    company = relationship("Company", back_populates="gias_accreditation")
    history = relationship(
        "GiasAccreditedCustomerHistory",
        back_populates="customer",
        cascade="all, delete-orphan",
    )


class GiasAccreditedCustomerHistory(Base):
    """Change history for GIAS accredited customers."""
    __tablename__ = "gias_accredited_customers_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("egr_companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    customer_id = Column(
        BigInteger,
        ForeignKey("gias_accredited_customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    unp = Column(String(20), nullable=False, index=True)
    change_type = Column(String(20), nullable=False, index=True)
    changed_fields = Column(JSONB, nullable=True)
    raw_json = Column(JSONB, nullable=True)
    observed_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    created_at = Column(DateTime, server_default=func.now())

    customer = relationship("GiasAccreditedCustomer", back_populates="history")


class LockedSupplierAuthor(Base):
    """Author directory for locked suppliers."""
    __tablename__ = "locked_supplier_authors"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid = Column(UUID(as_uuid=True), nullable=False, unique=True)
    initials = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class LockedSupplierReason(Base):
    """Include/exclude reasons for locked suppliers."""
    __tablename__ = "locked_supplier_reasons"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    kind = Column(String(16), nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("kind", "text", name="locked_supplier_reasons_kind_text_uniq"),
    )


class LockedSupplier(Base):
    """Current state of locked suppliers registry."""
    __tablename__ = "locked_suppliers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("egr_companies.id", ondelete="CASCADE"), nullable=True, index=True)
    uuid = Column(UUID(as_uuid=True), nullable=False, unique=True)
    chain_uuid = Column(UUID(as_uuid=True), nullable=False, index=True)
    author_id = Column(BigInteger, ForeignKey("locked_supplier_authors.id"), nullable=True)
    state = Column(String(32), nullable=False, index=True)
    name = Column(Text, nullable=False)
    provider_unp = Column(String(32), nullable=True, index=True)
    location = Column(Text, nullable=True)
    reg_number = Column(String(32), nullable=True)
    add_date = Column(DateTime, nullable=True)
    del_date = Column(DateTime, nullable=True)
    base_incl_id = Column(BigInteger, ForeignKey("locked_supplier_reasons.id"), nullable=True)
    base_excl_id = Column(BigInteger, ForeignKey("locked_supplier_reasons.id"), nullable=True)
    raw_json = Column(JSONB, nullable=True)
    sync_hash = Column(String(64), nullable=True)
    first_seen_at = Column(DateTime, nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    company = relationship("Company", back_populates="gias_locked_suppliers")
    author = relationship("LockedSupplierAuthor", foreign_keys=[author_id])
    base_incl = relationship("LockedSupplierReason", foreign_keys=[base_incl_id])
    base_excl = relationship("LockedSupplierReason", foreign_keys=[base_excl_id])
    history = relationship(
        "LockedSupplierHistory",
        back_populates="supplier",
        cascade="all, delete-orphan",
    )


class LockedSupplierHistory(Base):
    """Change history for locked suppliers."""
    __tablename__ = "locked_suppliers_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("egr_companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    supplier_id = Column(
        BigInteger,
        ForeignKey("locked_suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_unp = Column(String(32), nullable=True, index=True)
    supplier_name = Column(Text, nullable=False)
    chain_uuid = Column(UUID(as_uuid=True), nullable=False, index=True)
    change_type = Column(String(20), nullable=False, index=True)
    changed_fields = Column(JSONB, nullable=True)
    state = Column(String(32), nullable=False)
    location = Column(Text, nullable=True)
    reg_number = Column(String(32), nullable=True)
    add_date = Column(DateTime, nullable=True)
    del_date = Column(DateTime, nullable=True)
    base_incl_text = Column(Text, nullable=True)
    base_excl_text = Column(Text, nullable=True)
    raw_json = Column(JSONB, nullable=True)
    observed_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    created_at = Column(DateTime, server_default=func.now())

    supplier = relationship("LockedSupplier", back_populates="history")


# ---------------------------------------------------------------------------
# Bankrot.gov.by — дела о банкротстве
# ---------------------------------------------------------------------------

class BankrotCase(Base):
    """
    Дело о банкротстве из реестра bankrot.gov.by.

    Основные поля вынесены в отдельные колонки.
    Полные сырые ответы API сохраняются в JSONB:
      - list_data     — ответ из POST /v1/cases (элемент пагинированного списка)
      - detail_data   — ответ из GET  /v1/cases/{id}
      - judgements_group — ответ из GET /v1/cases/{id}/judgements/group

    Связь с EGR: debtor_unp → egr_companies.unp (мягкая, без FK,
    потому что компании может не быть в ЕГР).
    """
    __tablename__ = "bankrot_cases"

    # PK = case_id из API (integer)
    case_id = Column(Integer, primary_key=True, index=True)

    # Связь с организацией (мягкая — без FK, UNP может отсутствовать)
    debtor_unp = Column(BigInteger, nullable=True, index=True)

    # Основные поля дела
    number = Column(Text, nullable=True)           # номер дела, напр. "155НБ2682"
    start_date = Column(Date, nullable=True, index=True)
    end_date = Column(Date, nullable=True)
    status = Column(Integer, nullable=True, index=True)   # 0=closed, 1=active
    procedure_type = Column(Integer, nullable=True)       # 1=protective, 4=liquidation, …
    court = Column(Text, nullable=True)
    judge = Column(Text, nullable=True)

    # Управляющий
    manager_id = Column(Integer, nullable=True, index=True)
    manager_name = Column(Text, nullable=True)

    # Последнее судебное решение
    last_judgment_id = Column(BigInteger, nullable=True)

    # Сырые ответы API (JSONB — вся глубина без потерь)
    list_data = Column(JSONB, nullable=True)
    detail_data = Column(JSONB, nullable=True)
    judgements_group = Column(JSONB, nullable=True)

    # Ошибки при загрузке detail/judgements (не прерывают синхронизацию)
    fetch_error = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class BankrotCaseHistory(Base):
    """
    История изменений дел о банкротстве.

    Заполняется автоматически PostgreSQL-триггером trg_bankrot_cases_history:
    перед каждым UPDATE в bankrot_cases старая строка копируется сюда.
    Таблица только для чтения со стороны приложения.
    """
    __tablename__ = "bankrot_cases_history"

    history_id = Column(Integer, primary_key=True, autoincrement=True)

    # Ссылка на дело (без FK — строка в bankrot_cases могла быть удалена)
    case_id = Column(Integer, nullable=False, index=True)

    # Снимок всех полей на момент изменения
    debtor_unp       = Column(BigInteger, nullable=True)
    number           = Column(Text, nullable=True)
    start_date       = Column(Date, nullable=True)
    end_date         = Column(Date, nullable=True)
    status           = Column(Integer, nullable=True)
    procedure_type   = Column(Integer, nullable=True)
    court            = Column(Text, nullable=True)
    judge            = Column(Text, nullable=True)
    manager_id       = Column(Integer, nullable=True)
    manager_name     = Column(Text, nullable=True)
    last_judgment_id = Column(BigInteger, nullable=True)
    list_data        = Column(JSONB, nullable=True)
    detail_data      = Column(JSONB, nullable=True)
    judgements_group = Column(JSONB, nullable=True)
    fetch_error      = Column(Text, nullable=True)

    # Временны́е метки оригинальной строки
    case_created_at  = Column(DateTime, nullable=True)
    case_updated_at  = Column(DateTime, nullable=True)

    # Когда этот снимок был сохранён (заполняет триггер через server_default)
    recorded_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)


class BankrotSyncRun(Base):
    """
    Журнал запусков синхронизации bankrot.gov.by.
    Позволяет отслеживать прогресс и возобновлять после сбоя.
    """
    __tablename__ = "bankrot_sync_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String(32), nullable=False, default="running", index=True)

    started_at = Column(DateTime, nullable=False, server_default=func.now())
    finished_at = Column(DateTime, nullable=True)

    total_cases = Column(Integer, nullable=False, default=0)
    processed_cases = Column(Integer, nullable=False, default=0)
    failed_cases = Column(Integer, nullable=False, default=0)

    # Последняя успешно обработанная страница (для возобновления)
    last_page = Column(Integer, nullable=False, default=0)

    output_file = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    stats_json = Column(JSONB, nullable=True)


class GovOrganization(Base):
    """Справочник государственных организаций-юрлиц (классифицированных по имени/ОПФ).

    Самостоятельный справочник, наполняемый классификатором поверх собранных данных
    (egr_raw_company_data + grp_taxpayer_data). Ключ — УНП. FK к egr_companies НЕТ:
    чистые госорганы (сельисполкомы/Советы) в ЕГР отсутствуют и приходят из ГРП.
    """
    __tablename__ = "gov_organizations"

    unp = Column(BigInteger, primary_key=True, index=True)
    # Ссылка на центральный реестр (egr_companies). Все УНП живут там; здесь —
    # только классификация поверх.
    company_id = Column(UUID(as_uuid=True), ForeignKey("egr_companies.id", ondelete="CASCADE"), nullable=True, index=True)
    full_name = Column(Text, nullable=True)
    short_name = Column(Text, nullable=True)

    # ОПФ из ЕГР (nsi00203), если запись пришла из egr_raw; для ГРП-источника пусто
    opf_code = Column(Integer, nullable=True, index=True)
    opf_name = Column(Text, nullable=True)

    # local_council | gov_body | gov_institution | unitary_enterprise | joint_stock | other_state
    category = Column(String(32), nullable=False, index=True)
    # state (республиканская) | communal (коммунальная) | unknown
    ownership = Column(String(16), nullable=False, index=True)
    # egr | grp — откуда классифицирована запись
    source = Column(String(8), nullable=False, index=True)
    # маркер, по которому сработала классификация (для отладки/тюнинга)
    matched_marker = Column(Text, nullable=True)

    classified_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
