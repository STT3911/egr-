"""Объяснимый риск-скоринг контрагента по данным локальной БД."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database.models import (
    BankrotCase,
    BankrotSyncRun,
    Company,
    CompanyAddressHistory,
    CompanyAddressKey,
    CompanyNameHistory,
    EAEUSEZResidentRecord,
    GiasAccreditedCustomer,
    GiasSyncRun,
    LicenseRecord,
    LockedSupplier,
    NalogDebtRecord,
    PVTResidentRecord,
    ReferenceStatus,
    SystemState,
)

MASS_ADDRESS_WARN = 10
MASS_ADDRESS_HIGH = 50
FREQUENT_ADDR_CHANGES = 3
FREQUENT_NAME_CHANGES = 2
YOUNG_COMPANY_DAYS = 180
RECENT_WINDOW_DAYS = 730

LEVEL_HIGH = 50
LEVEL_MEDIUM = 20
TAX_DEBT_CURRENT_WEIGHT = 25

CATEGORY_META = {
    "legal": {"title": "Правовой статус", "cap": 70},
    "fiscal": {"title": "Налоговая дисциплина", "cap": 25},
    "compliance": {"title": "Реестры ограничений", "cap": 35},
    "behavioral": {"title": "Поведенческие сигналы", "cap": 25},
}


def _to_iso(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat().replace("+00:00", "Z")
    return value.isoformat()


def _factor(
    code: str,
    title: str,
    weight: int,
    detail: str,
    *,
    category: str,
    severity: str,
    source: str,
    observed_at: date | datetime | None = None,
) -> Dict[str, Any]:
    return {
        "code": code,
        "title": title,
        "weight": weight,
        "detail": detail,
        "category": category,
        "severity": severity,
        "source": source,
        "observed_at": _to_iso(observed_at),
    }


def _trust_factor(
    code: str,
    title: str,
    detail: str,
    *,
    source: str,
    observed_at: date | datetime | None = None,
) -> Dict[str, Any]:
    return _factor(
        code,
        title,
        0,
        detail,
        category="trust",
        severity="positive",
        source=source,
        observed_at=observed_at,
    )


def _days_ago(days: int) -> date:
    return date.today() - timedelta(days=days)


def _historical_tax_weight(slice_date: date) -> int:
    age_days = max(0, (date.today() - slice_date).days)
    if age_days <= 365:
        return 10
    if age_days <= 730:
        return 7
    return 4


def _tax_debt_factors(
    db: Session,
    unp: int,
    latest_slice: date | None,
) -> List[Dict[str, Any]]:
    company_debt_slice = (
        db.query(func.max(NalogDebtRecord.slice_date))
        .filter(NalogDebtRecord.debtor_unp == unp)
        .scalar()
    )
    if company_debt_slice is None:
        return []

    debt_rows = (
        db.query(func.count(NalogDebtRecord.id))
        .filter(
            NalogDebtRecord.debtor_unp == unp,
            NalogDebtRecord.slice_date == company_debt_slice,
        )
        .scalar()
    ) or 0
    if not debt_rows:
        return []

    if latest_slice is not None and company_debt_slice == latest_slice:
        return [
            _factor(
                "tax_debt",
                "Актуальная налоговая задолженность",
                TAX_DEBT_CURRENT_WEIGHT,
                f"Записей в срезе МНС от {company_debt_slice.isoformat()}: {debt_rows}",
                category="fiscal",
                severity="high",
                source="МНС",
                observed_at=company_debt_slice,
            )
        ]

    historical_weight = _historical_tax_weight(company_debt_slice)
    return [
        _factor(
            "tax_debt_history",
            "Задолженность МНС в истории",
            historical_weight,
            f"Последний срез с задолженностью: {company_debt_slice.isoformat()}, записей: {debt_rows}",
            category="fiscal",
            severity="medium" if historical_weight >= 7 else "low",
            source="МНС",
            observed_at=company_debt_slice,
        )
    ]


def _latest_finished_run(
    db: Session,
    model,
    successful_statuses: tuple[str, ...],
    *,
    registry_name: str | None = None,
) -> datetime | None:
    query = db.query(func.max(model.finished_at)).filter(model.status.in_(successful_statuses))
    if registry_name is not None:
        query = query.filter(model.registry_name == registry_name)
    return query.scalar()


def _coverage_source(
    code: str,
    title: str,
    weight: int,
    checked_at: date | datetime | None,
    max_age_days: int,
) -> Dict[str, Any]:
    fresh = False
    if checked_at is not None:
        if isinstance(checked_at, datetime):
            checked_datetime = checked_at
            if checked_datetime.tzinfo is None:
                checked_datetime = checked_datetime.replace(tzinfo=timezone.utc)
        else:
            checked_datetime = datetime.combine(checked_at, datetime.min.time(), tzinfo=timezone.utc)
        fresh = datetime.now(timezone.utc) - checked_datetime <= timedelta(days=max_age_days)
    earned_weight = weight if fresh else weight // 2 if checked_at is not None else 0
    return {
        "code": code,
        "title": title,
        "weight": weight,
        "earned_weight": earned_weight,
        "available": checked_at is not None,
        "fresh": fresh,
        "status": "fresh" if fresh else "stale" if checked_at is not None else "missing",
        "checked_at": _to_iso(checked_at),
    }


def _build_coverage(
    db: Session,
    company: Company,
    latest_tax_slice: date | None,
    address_checked_at: datetime | None,
) -> Dict[str, Any]:
    bankrot_checked_at = _latest_finished_run(db, BankrotSyncRun, ("done",))
    mart_checked_at = _latest_finished_run(
        db,
        GiasSyncRun,
        ("success",),
        registry_name="locked_suppliers",
    )
    egr_state = db.query(SystemState).filter(SystemState.key == "egr_last_sync_date").first()
    egr_checked_at = egr_state.updated_at if egr_state else company.updated_at or company.created_at
    sources = [
        _coverage_source("egr", "Статус и история ЕГР", 25, egr_checked_at, 30),
        _coverage_source("bankruptcy", "Реестр банкротств", 25, bankrot_checked_at, 3),
        _coverage_source("tax_debt", "Задолженность МНС", 25, latest_tax_slice, 45),
        _coverage_source("locked_suppliers", "Ограничения МАРТ", 15, mart_checked_at, 14),
        _coverage_source("address_cluster", "Кластер юридического адреса", 10, address_checked_at, 45),
    ]
    score = sum(source["earned_weight"] for source in sources)
    if score >= 80:
        level = "high"
    elif score >= 60:
        level = "medium"
    else:
        level = "low"
    return {
        "score": score,
        "level": level,
        "checked_sources": sum(1 for source in sources if source["available"]),
        "total_sources": len(sources),
        "sources": sources,
        "missing_sources": [source["title"] for source in sources if not source["available"]],
        "stale_sources": [source["title"] for source in sources if source["status"] == "stale"],
    }


def _build_categories(factors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    categories: List[Dict[str, Any]] = []
    for code, meta in CATEGORY_META.items():
        category_factors = [factor for factor in factors if factor["category"] == code]
        raw_score = sum(factor["weight"] for factor in category_factors)
        capped_score = min(meta["cap"], raw_score)
        ratio = capped_score / meta["cap"] if meta["cap"] else 0
        categories.append(
            {
                "code": code,
                "title": meta["title"],
                "score": capped_score,
                "raw_score": raw_score,
                "cap": meta["cap"],
                "level": "high" if ratio >= 0.67 else "medium" if ratio >= 0.34 else "low",
                "factor_count": len(category_factors),
            }
        )
    return categories


def _decision(
    score: int,
    level: str,
    critical_flags: List[str],
    coverage_score: int,
) -> tuple[str, str, str]:
    if critical_flags:
        return (
            "stop",
            "Обнаружен стоп-фактор",
            "До сделки нужна обязательная ручная проверка и подтверждающие документы.",
        )
    if level == "high":
        return (
            "manual_review",
            "Высокий риск",
            "Совокупность независимых сигналов требует углублённой проверки.",
        )
    if coverage_score < 60:
        return (
            "incomplete",
            "Недостаточно данных",
            "Оценка предварительная: часть ключевых источников ещё не проверена.",
        )
    if level == "medium":
        return (
            "review",
            "Есть сигналы к проверке",
            "Перед сделкой проверьте отмеченные факторы и их актуальность.",
        )
    return (
        "clear",
        "Явных стоп-сигналов нет",
        "По доступным источникам критические факторы не обнаружены.",
    )


def compute_risk(db: Session, unp: int) -> Optional[Dict[str, Any]]:
    """Вернуть объяснимый риск-профиль компании или ``None`` для неизвестного УНП."""
    try:
        unp_int = int(unp)
    except (TypeError, ValueError):
        return None

    company: Optional[Company] = db.query(Company).filter(Company.unp == unp_int).first()
    if company is None:
        return None

    unp_str = str(unp_int)
    factors: List[Dict[str, Any]] = []
    trust: List[Dict[str, Any]] = []

    active_bankrot = (
        db.query(func.count(BankrotCase.case_id))
        .filter(BankrotCase.debtor_unp == unp_int, BankrotCase.status == 1)
        .scalar()
    ) or 0
    total_bankrot = (
        db.query(func.count(BankrotCase.case_id))
        .filter(BankrotCase.debtor_unp == unp_int)
        .scalar()
    ) or 0
    latest_bankrot_date = (
        db.query(func.max(BankrotCase.updated_at))
        .filter(BankrotCase.debtor_unp == unp_int)
        .scalar()
    )
    if active_bankrot:
        factors.append(
            _factor(
                "bankruptcy_active",
                "Активное дело о банкротстве",
                60,
                f"Открытых дел: {active_bankrot}",
                category="legal",
                severity="critical",
                source="bankrot.gov.by",
                observed_at=latest_bankrot_date,
            )
        )
    elif total_bankrot:
        factors.append(
            _factor(
                "bankruptcy_past",
                "Банкротство в истории",
                18,
                f"Завершённых дел: {total_bankrot}",
                category="legal",
                severity="medium",
                source="bankrot.gov.by",
                observed_at=latest_bankrot_date,
            )
        )

    latest_tax_slice = db.query(func.max(NalogDebtRecord.slice_date)).scalar()
    factors.extend(_tax_debt_factors(db, unp_int, latest_tax_slice))

    locked_active = (
        db.query(func.count(LockedSupplier.id))
        .filter(LockedSupplier.provider_unp == unp_str, LockedSupplier.del_date.is_(None))
        .scalar()
    ) or 0
    latest_locked_date = (
        db.query(func.max(LockedSupplier.last_seen_at))
        .filter(LockedSupplier.provider_unp == unp_str)
        .scalar()
    )
    if locked_active:
        factors.append(
            _factor(
                "locked_supplier",
                "Действующая запись в реестре МАРТ",
                35,
                f"Активных записей: {locked_active}",
                category="compliance",
                severity="high",
                source="ГИАС / МАРТ",
                observed_at=latest_locked_date,
            )
        )

    status_name = None
    if company.current_status_code is not None:
        status_name = (
            db.query(ReferenceStatus.name)
            .filter(ReferenceStatus.id == company.current_status_code)
            .scalar()
        )
    normalized_status = (status_name or "").lower()
    terminal_status = any(
        marker in normalized_status
        for marker in ("ликвидирован", "исключен", "исключён", "прекращен", "прекращён")
    )
    process_status = any(
        marker in normalized_status for marker in ("ликвидац", "реорганизац", "прекращения")
    )
    if company.liquidation_date is not None or terminal_status:
        liquidation_detail = (
            f"Дата ликвидации: {company.liquidation_date.isoformat()}"
            if company.liquidation_date is not None
            else status_name or "Статус прекращения деятельности"
        )
        factors.append(
            _factor(
                "liquidated",
                "Деятельность прекращена",
                60,
                liquidation_detail,
                category="legal",
                severity="critical",
                source="ЕГР",
                observed_at=company.liquidation_date or company.updated_at,
            )
        )
    elif process_status:
        factors.append(
            _factor(
                "in_liquidation",
                "Процесс ликвидации или реорганизации",
                40,
                status_name or "Статус ЕГР",
                category="legal",
                severity="high",
                source="ЕГР",
                observed_at=company.updated_at,
            )
        )

    address_row = (
        db.query(CompanyAddressKey.address_key, CompanyAddressKey.last_seen_at)
        .filter(CompanyAddressKey.company_id == company.id)
        .first()
    )
    if address_row and address_row[0]:
        same_addr = (
            db.query(func.count(CompanyAddressKey.company_id))
            .filter(CompanyAddressKey.address_key == address_row[0])
            .scalar()
        ) or 0
        if same_addr >= MASS_ADDRESS_HIGH:
            factors.append(
                _factor(
                    "mass_address_high",
                    "Критически массовый адрес",
                    15,
                    f"По адресу зарегистрировано компаний: {same_addr}",
                    category="behavioral",
                    severity="high",
                    source="ЕГР",
                    observed_at=address_row[1],
                )
            )
        elif same_addr >= MASS_ADDRESS_WARN:
            factors.append(
                _factor(
                    "mass_address",
                    "Массовый адрес регистрации",
                    8,
                    f"По адресу зарегистрировано компаний: {same_addr}",
                    category="behavioral",
                    severity="medium",
                    source="ЕГР",
                    observed_at=address_row[1],
                )
            )

    window = _days_ago(RECENT_WINDOW_DAYS)
    addr_changes = (
        db.query(func.count(CompanyAddressHistory.id))
        .filter(
            CompanyAddressHistory.company_id == company.id,
            CompanyAddressHistory.valid_to.isnot(None),
            CompanyAddressHistory.valid_to >= window,
        )
        .scalar()
    ) or 0
    if addr_changes >= FREQUENT_ADDR_CHANGES:
        factors.append(
            _factor(
                "frequent_address_change",
                "Частая смена юридического адреса",
                8,
                f"Смен адреса за 2 года: {addr_changes}",
                category="behavioral",
                severity="medium",
                source="ЕГР",
                observed_at=company.updated_at,
            )
        )

    name_changes = (
        db.query(func.count(CompanyNameHistory.id))
        .filter(
            CompanyNameHistory.company_id == company.id,
            CompanyNameHistory.valid_to.isnot(None),
            CompanyNameHistory.valid_to >= window,
        )
        .scalar()
    ) or 0
    if name_changes >= FREQUENT_NAME_CHANGES:
        factors.append(
            _factor(
                "frequent_name_change",
                "Частая смена наименования",
                6,
                f"Смен наименования за 2 года: {name_changes}",
                category="behavioral",
                severity="medium",
                source="ЕГР",
                observed_at=company.updated_at,
            )
        )

    if company.registration_date is not None:
        age_days = (date.today() - company.registration_date).days
        if 0 <= age_days < YOUNG_COMPANY_DAYS:
            factors.append(
                _factor(
                    "young_company",
                    "Недавно зарегистрирована",
                    6,
                    f"Возраст компании: {age_days} дн.",
                    category="behavioral",
                    severity="low",
                    source="ЕГР",
                    observed_at=company.registration_date,
                )
            )
        years = age_days // 365
        if years >= 10:
            trust.append(
                _trust_factor(
                    "established",
                    "Работает более 10 лет",
                    f"Возраст: около {years} лет",
                    source="ЕГР",
                    observed_at=company.registration_date,
                )
            )

    active_licenses = (
        db.query(func.count(LicenseRecord.id))
        .filter(LicenseRecord.holder_unp == unp_int, LicenseRecord.activity_is_active.is_(True))
        .scalar()
    ) or 0
    if active_licenses:
        trust.append(
            _trust_factor(
                "licensed",
                "Есть действующие лицензии",
                f"Активных лицензий: {active_licenses}",
                source="license.gov.by",
            )
        )

    pvt_row = db.query(PVTResidentRecord).filter(PVTResidentRecord.unp == unp_int).first()
    if pvt_row:
        trust.append(
            _trust_factor(
                "pvt_resident",
                "Резидент ПВТ",
                "Парк высоких технологий",
                source="park.by",
                observed_at=pvt_row.last_seen_at,
            )
        )
    sez_row = (
        db.query(EAEUSEZResidentRecord)
        .filter(EAEUSEZResidentRecord.unp == unp_int)
        .order_by(EAEUSEZResidentRecord.last_seen_at.desc())
        .first()
    )
    if sez_row:
        trust.append(
            _trust_factor(
                "sez_resident",
                "Резидент СЭЗ ЕАЭС",
                "Свободная экономическая зона",
                source="ЕАЭС",
                observed_at=sez_row.last_seen_at,
            )
        )
    gias_row = (
        db.query(GiasAccreditedCustomer)
        .filter(
            GiasAccreditedCustomer.unp == unp_str,
            or_(GiasAccreditedCustomer.dt_to.is_(None), GiasAccreditedCustomer.dt_to >= datetime.utcnow()),
        )
        .first()
    )
    if gias_row:
        trust.append(
            _trust_factor(
                "gias_accredited",
                "Аккредитованный заказчик ГИАС",
                gias_row.state or "Государственные закупки",
                source="ГИАС",
                observed_at=gias_row.last_seen_at,
            )
        )

    factors.sort(key=lambda factor: factor["weight"], reverse=True)
    categories = _build_categories(factors)
    score = min(100, sum(category["score"] for category in categories))
    level = "high" if score >= LEVEL_HIGH else "medium" if score >= LEVEL_MEDIUM else "low"
    critical_flags = [factor["code"] for factor in factors if factor["severity"] == "critical"]
    coverage = _build_coverage(
        db,
        company,
        latest_tax_slice,
        address_row[1] if address_row else None,
    )
    decision, decision_label, summary = _decision(
        score,
        level,
        critical_flags,
        coverage["score"],
    )

    return {
        "unp": unp_int,
        "score": score,
        "level": level,
        "decision": decision,
        "decision_label": decision_label,
        "summary": summary,
        "critical_flags": critical_flags,
        "categories": categories,
        "factors": factors,
        "trust_signals": trust,
        "coverage": coverage,
        "methodology_version": "2.0",
        "computed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
