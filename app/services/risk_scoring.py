"""Риск-скоринг контрагента по УНП.

Собирает сигналы из всех источников, накопленных в базе (банкротство, задолженность
МНС, реестр недобросовестных поставщиков МАРТ, статус/ликвидация ЕГР, массовый адрес,
частые смены адреса/названия, возраст), и считает объяснимую оценку риска 0–100.

Принципы:
  • Прозрачность: каждый фактор возвращается отдельно — вес и человекочитаемая причина.
    Итог = сумма весов риск-факторов (обрезается до 100). Никакого ML/чёрных ящиков.
  • Плюс-факторы (лицензии, резидент ПВТ/СЭЗ, аккредитация ГИАС, возраст) не уменьшают
    число, а показываются отдельным списком «сигналы доверия» — чтобы «почему 68?»
    всегда имело однозначный ответ.

Данные только из локальной БД (без обращений во внешние API) — быстро и годится
для показа прямо в карточке компании.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.models import (
    BankrotCase,
    Company,
    CompanyAddressHistory,
    CompanyAddressKey,
    CompanyNameHistory,
    EAEUSEZResidentRecord,
    GiasAccreditedCustomer,
    LicenseRecord,
    LockedSupplier,
    NalogDebtRecord,
    PVTResidentRecord,
    ReferenceStatus,
)

# Пороги (вынесены сюда — легко тюнить без переписывания логики).
MASS_ADDRESS_WARN = 10       # компаний на одном адресе — жёлтый сигнал
MASS_ADDRESS_HIGH = 50       # массовый адрес — красный сигнал
FREQUENT_ADDR_CHANGES = 3    # смен адреса за 2 года
FREQUENT_NAME_CHANGES = 2    # смен наименования за 2 года
YOUNG_COMPANY_DAYS = 180     # «молодая» компания
RECENT_WINDOW_DAYS = 730     # окно «за последние 2 года»

LEVEL_HIGH = 50
LEVEL_MEDIUM = 25


def _factor(code: str, title: str, weight: int, detail: str) -> Dict[str, Any]:
    return {"code": code, "title": title, "weight": weight, "detail": detail}


def _days_ago(days: int) -> date:
    return date.today() - timedelta(days=days)


def compute_risk(db: Session, unp: int) -> Optional[Dict[str, Any]]:
    """Посчитать риск-профиль компании по УНП.

    Returns:
        dict с полями score/level/factors/trust_signals/computed_at,
        либо None, если компании с таким УНП нет в ЕГР.
    """
    try:
        unp_int = int(unp)
    except (TypeError, ValueError):
        return None

    company: Optional[Company] = (
        db.query(Company).filter(Company.unp == unp_int).first()
    )
    if company is None:
        return None

    unp_str = str(unp_int)
    factors: List[Dict[str, Any]] = []
    trust: List[Dict[str, Any]] = []

    # --- Банкротство --------------------------------------------------
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
    if active_bankrot:
        # Активное банкротство — само по себе стоп-фактор: одного его достаточно
        # для уровня «высокий» (вес ≥ LEVEL_HIGH).
        factors.append(_factor(
            "bankruptcy_active", "Активное дело о банкротстве", 50,
            f"Открытых дел: {active_bankrot}",
        ))
    elif total_bankrot:
        factors.append(_factor(
            "bankruptcy_past", "Дело о банкротстве в истории", 15,
            f"Завершённых дел: {total_bankrot}",
        ))

    # --- Налоговая задолженность (МНС) --------------------------------
    latest_slice = db.query(func.max(NalogDebtRecord.slice_date)).scalar()
    if latest_slice is not None:
        debt_rows = (
            db.query(func.count(NalogDebtRecord.id))
            .filter(
                NalogDebtRecord.debtor_unp == unp_int,
                NalogDebtRecord.slice_date == latest_slice,
            )
            .scalar()
        ) or 0
        if debt_rows:
            factors.append(_factor(
                "tax_debt", "Налоговая задолженность (МНС)", 20,
                f"Записей в срезе {latest_slice.isoformat()}: {debt_rows}",
            ))

    # --- Реестр недобросовестных поставщиков (МАРТ) -------------------
    locked_active = (
        db.query(func.count(LockedSupplier.id))
        .filter(
            LockedSupplier.provider_unp == unp_str,
            LockedSupplier.del_date.is_(None),
        )
        .scalar()
    ) or 0
    if locked_active:
        factors.append(_factor(
            "locked_supplier", "В реестре недобросовестных поставщиков (МАРТ)", 25,
            "Действующая запись в реестре",
        ))

    # --- Статус / ликвидация (ЕГР) ------------------------------------
    if company.liquidation_date is not None:
        factors.append(_factor(
            "liquidated", "Ликвидирована / исключена", 30,
            f"Дата ликвидации: {company.liquidation_date.isoformat()}",
        ))
    else:
        status_name = None
        if company.current_status_code is not None:
            status_name = (
                db.query(ReferenceStatus.name)
                .filter(ReferenceStatus.id == company.current_status_code)
                .scalar()
            )
        if status_name and "ликвидац" in status_name.lower():
            factors.append(_factor(
                "in_liquidation", "В процессе ликвидации/реорганизации", 20,
                status_name,
            ))

    # --- Массовый адрес -----------------------------------------------
    addr_key_row = (
        db.query(CompanyAddressKey.address_key)
        .filter(CompanyAddressKey.company_id == company.id)
        .first()
    )
    if addr_key_row and addr_key_row[0]:
        same_addr = (
            db.query(func.count(CompanyAddressKey.company_id))
            .filter(CompanyAddressKey.address_key == addr_key_row[0])
            .scalar()
        ) or 0
        if same_addr >= MASS_ADDRESS_HIGH:
            factors.append(_factor(
                "mass_address_high", "Массовый адрес регистрации", 15,
                f"По этому адресу зарегистрировано компаний: {same_addr}",
            ))
        elif same_addr >= MASS_ADDRESS_WARN:
            factors.append(_factor(
                "mass_address", "Много компаний на одном адресе", 8,
                f"По этому адресу зарегистрировано компаний: {same_addr}",
            ))

    # --- Частые смены адреса / названия (за 2 года) -------------------
    window = _days_ago(RECENT_WINDOW_DAYS)
    addr_changes = (
        db.query(func.count(CompanyAddressHistory.id))
        .filter(
            CompanyAddressHistory.company_id == company.id,
            CompanyAddressHistory.valid_from >= window,
        )
        .scalar()
    ) or 0
    if addr_changes >= FREQUENT_ADDR_CHANGES:
        factors.append(_factor(
            "frequent_address_change", "Частая смена юридического адреса", 8,
            f"Смен адреса за 2 года: {addr_changes}",
        ))

    name_changes = (
        db.query(func.count(CompanyNameHistory.id))
        .filter(
            CompanyNameHistory.company_id == company.id,
            CompanyNameHistory.valid_from >= window,
        )
        .scalar()
    ) or 0
    if name_changes >= FREQUENT_NAME_CHANGES:
        factors.append(_factor(
            "frequent_name_change", "Частая смена наименования", 6,
            f"Смен наименования за 2 года: {name_changes}",
        ))

    # --- Молодая компания ---------------------------------------------
    if company.registration_date is not None:
        age_days = (date.today() - company.registration_date).days
        if 0 <= age_days < YOUNG_COMPANY_DAYS:
            factors.append(_factor(
                "young_company", "Недавно зарегистрирована", 8,
                f"Возраст: {age_days} дн.",
            ))

    # --- Плюс-факторы (сигналы доверия) -------------------------------
    if company.registration_date is not None:
        years = (date.today() - company.registration_date).days // 365
        if years >= 10:
            trust.append(_factor("established", "Работает более 10 лет", 0, f"Возраст: ~{years} лет"))

    active_lic = (
        db.query(func.count(LicenseRecord.id))
        .filter(LicenseRecord.holder_unp == unp_int, LicenseRecord.activity_is_active.is_(True))
        .scalar()
    ) or 0
    if active_lic:
        trust.append(_factor("licensed", "Есть действующие лицензии", 0, f"Активных лицензий: {active_lic}"))

    if db.query(PVTResidentRecord.unp).filter(PVTResidentRecord.unp == unp_int).first():
        trust.append(_factor("pvt_resident", "Резидент ПВТ", 0, "Парк высоких технологий"))
    if db.query(EAEUSEZResidentRecord.unp).filter(EAEUSEZResidentRecord.unp == unp_int).first():
        trust.append(_factor("sez_resident", "Резидент СЭЗ ЕАЭС", 0, "Свободная экономическая зона"))
    if db.query(GiasAccreditedCustomer.unp).filter(GiasAccreditedCustomer.unp == unp_str).first():
        trust.append(_factor("gias_accredited", "Аккредитованный заказчик (ГИАС)", 0, "Госзакупки"))

    # --- Итог ----------------------------------------------------------
    score = min(100, sum(f["weight"] for f in factors))
    if score >= LEVEL_HIGH:
        level = "high"
    elif score >= LEVEL_MEDIUM:
        level = "medium"
    else:
        level = "low"

    # Сортируем факторы по весу — самые значимые сверху.
    factors.sort(key=lambda f: f["weight"], reverse=True)

    return {
        "unp": unp_int,
        "score": score,
        "level": level,
        "factors": factors,
        "trust_signals": trust,
        "computed_at": datetime.utcnow().isoformat() + "Z",
    }
