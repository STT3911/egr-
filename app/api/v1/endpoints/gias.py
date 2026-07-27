"""GIAS registry endpoints."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.security import verify_api_key
from app.database.models import (
    GiasAccreditedCustomer,
    GiasAccreditedCustomerHistory,
    GiasSyncRun,
    GiasContract,
    LockedSupplier,
    LockedSupplierHistory,
)
from app.schemas.gias import (
    GiasAccreditedCustomerHistorySchema,
    GiasAccreditedCustomerSchema,
    GiasContractDetailSchema,
    GiasSyncRunSchema,
    GiasSyncTriggerResponse,
    GiasContractSchema,
    LockedSupplierHistorySchema,
    LockedSupplierSchema,
)
from app.tasks.sync_tasks import (
    fetch_gias_contract_details,
    resolve_gias_contract_companies,
    sync_gias_contract_index,
    sync_gias_directory_registries,
)

router = APIRouter()


@router.post("/contracts/sync", response_model=GiasSyncTriggerResponse)
def trigger_contract_sync(
    full: bool = Query(False),
    max_pages: Optional[int] = Query(None, ge=1),
    api_key: str = Depends(verify_api_key),
):
    task = sync_gias_contract_index.delay(full, max_pages)
    return GiasSyncTriggerResponse(status="queued", task_id=task.id)


@router.post("/contracts/fetch-details", response_model=GiasSyncTriggerResponse)
def trigger_contract_details(
    batch_size: Optional[int] = Query(None, ge=1, le=1000),
    api_key: str = Depends(verify_api_key),
):
    task = fetch_gias_contract_details.delay(batch_size)
    return GiasSyncTriggerResponse(status="queued", task_id=task.id)


@router.post("/contracts/resolve-companies", response_model=GiasSyncTriggerResponse)
def trigger_contract_company_resolution(
    batch_size: Optional[int] = Query(None, ge=1, le=500),
    api_key: str = Depends(verify_api_key),
):
    task = resolve_gias_contract_companies.delay(batch_size)
    return GiasSyncTriggerResponse(status="queued", task_id=task.id)


@router.get("/contracts", response_model=list[GiasContractSchema])
def list_contracts(
    unp: Optional[int] = Query(None, ge=1),
    role: Optional[str] = Query(None, pattern="^(customer|provider)$"),
    q: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(GiasContract)
    if unp is not None:
        if role == "customer":
            query = query.filter(GiasContract.customer_unp == unp)
        elif role == "provider":
            query = query.filter(GiasContract.provider_unp == unp)
        else:
            query = query.filter(
                or_(
                    GiasContract.customer_unp == unp,
                    GiasContract.provider_unp == unp,
                )
            )
    if q:
        value = f"%{q.strip()}%"
        query = query.filter(
            or_(
                GiasContract.title.ilike(value),
                GiasContract.registration_number.ilike(value),
                GiasContract.contract_number.ilike(value),
            )
        )
    if state:
        query = query.filter(GiasContract.state == state)
    return (
        query.order_by(GiasContract.source_updated_at.desc().nullslast())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/contracts/{contract_id}", response_model=GiasContractDetailSchema)
def get_contract(
    contract_id: UUID,
    db: Session = Depends(get_db),
):
    contract = (
        db.query(GiasContract)
        .options(selectinload(GiasContract.positions))
        .filter(GiasContract.contract_id == contract_id)
        .one_or_none()
    )
    if contract is None:
        raise HTTPException(status_code=404, detail="Договор GIAS не найден")
    return contract


@router.get("/sync-runs", response_model=list[GiasSyncRunSchema])
def get_sync_runs(
    registry_name: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(GiasSyncRun).order_by(desc(GiasSyncRun.started_at))
    if registry_name:
        query = query.filter(GiasSyncRun.registry_name == registry_name)
    return query.limit(limit).all()


@router.post("/sync", response_model=GiasSyncTriggerResponse)
def trigger_sync(
    async_run: bool = Query(True, description="Запускать через Celery"),
    api_key: str = Depends(verify_api_key),
):
    if async_run:
        task = sync_gias_directory_registries.delay()
        return GiasSyncTriggerResponse(status="queued", task_id=task.id)
    result = sync_gias_directory_registries()
    return GiasSyncTriggerResponse(status="completed", result=result)


@router.get("/accredited-customers", response_model=list[GiasAccreditedCustomerSchema])
def list_accredited_customers(
    q: Optional[str] = Query(None, description="Поиск по УНП или названию"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(GiasAccreditedCustomer).order_by(GiasAccreditedCustomer.name.asc())
    if q:
        q = q.strip()
        query = query.filter(
            (GiasAccreditedCustomer.unp.ilike(f"{q}%"))
            | (GiasAccreditedCustomer.name.ilike(f"%{q}%"))
        )
    return query.limit(limit).all()


@router.get(
    "/accredited-customers/{unp}/history",
    response_model=list[GiasAccreditedCustomerHistorySchema],
)
def get_accredited_customer_history(
    unp: str = Path(..., pattern=r"^\d{1,20}$"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    customer = db.query(GiasAccreditedCustomer).filter(GiasAccreditedCustomer.unp == unp).one_or_none()
    if customer is None:
        raise HTTPException(status_code=404, detail="Аккредитованное лицо не найдено")

    return (
        db.query(GiasAccreditedCustomerHistory)
        .filter(GiasAccreditedCustomerHistory.customer_id == customer.id)
        .order_by(desc(GiasAccreditedCustomerHistory.observed_at))
        .limit(limit)
        .all()
    )


@router.get("/locked-suppliers", response_model=list[LockedSupplierSchema])
def list_locked_suppliers(
    q: Optional[str] = Query(None, description="Поиск по УНП или названию"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(LockedSupplier)
        .order_by(LockedSupplier.add_date.desc().nullslast(), LockedSupplier.name.asc())
    )
    if q:
        q = q.strip()
        rows = rows.filter(
            (LockedSupplier.provider_unp.ilike(f"{q}%"))
            | (LockedSupplier.name.ilike(f"%{q}%"))
        )

    suppliers = rows.limit(limit).all()
    result: list[LockedSupplierSchema] = []
    for item in suppliers:
        result.append(
            LockedSupplierSchema(
                uuid=str(item.uuid),
                chain_uuid=str(item.chain_uuid),
                state=item.state,
                name=item.name,
                provider_unp=item.provider_unp,
                location=item.location,
                reg_number=item.reg_number,
                add_date=item.add_date,
                del_date=item.del_date,
                base_incl_text=item.base_incl.text if item.base_incl else None,
                base_excl_text=item.base_excl.text if item.base_excl else None,
                author_initials=item.author.initials if item.author else None,
                author_summary=item.author.summary if item.author else None,
                first_seen_at=item.first_seen_at,
                last_seen_at=item.last_seen_at,
                updated_at=item.updated_at,
            )
        )
    return result


@router.get("/locked-suppliers/{unp}/history", response_model=list[LockedSupplierHistorySchema])
def get_locked_supplier_history(
    unp: str = Path(..., pattern=r"^\d{1,20}$"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    history = (
        db.query(LockedSupplierHistory)
        .filter(LockedSupplierHistory.provider_unp == unp)
        .order_by(desc(LockedSupplierHistory.observed_at))
        .limit(limit)
        .all()
    )
    if not history:
        raise HTTPException(status_code=404, detail="История по поставщику не найдена")
    return history
