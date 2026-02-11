"""API endpoints for MNS GRP taxpayer data (налоговая)."""

from __future__ import annotations

from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import verify_api_key
from app.crud.grp import GrpCRUD
from app.schemas.grp import GrpTaxpayerDataResponse
from app.services.grp_client import GRPClient
from app.utils.address_formatter import format_grp_address


router = APIRouter()


def _serialize(record, raw_record=None) -> GrpTaxpayerDataResponse:
    """record — GrpTaxpayerData; raw_record — опционально GrpRawData для http_status/last_error/raw.
    У GrpTaxpayerData нет http_status/last_error/raw — только у GrpRawData; используем getattr чтобы не падать.
    """
    http_status = None
    last_error = None
    raw = None
    if raw_record is not None:
        http_status = getattr(raw_record, "http_status", None)
        last_error = getattr(raw_record, "last_error", None)
        raw = getattr(raw_record, "raw_json", None)
    return GrpTaxpayerDataResponse(
        unp=int(record.unp),
        full_name=record.full_name,
        short_name=record.short_name,
        registration_date=record.registration_date.isoformat() if record.registration_date else None,
        inspectorate_code=record.inspectorate_code,
        inspectorate_name=record.inspectorate_name,
        status_code=record.status_code,
        status_date=record.status_date.isoformat() if record.status_date else None,
        address=format_grp_address(record.address),
        fetched_at=record.fetched_at.isoformat() if record.fetched_at else None,
        updated_at=record.updated_at.isoformat() if record.updated_at else None,
        http_status=http_status,
        last_error=last_error,
        raw=raw,
    )


@router.get("/{unp}", response_model=GrpTaxpayerDataResponse)
async def get_grp_data(
    unp: int,
    force_refresh: bool = Query(False, description="Если true — сходить в GRP и обновить запись"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Get GRP taxpayer data for a UNP.

    By default returns cached DB record (if present).
    If force_refresh=true (or record missing) — fetches from GRP API and stores.
    """
    crud = GrpCRUD(db)
    record = crud.get_by_unp(unp)

    if force_refresh or record is None:
        client = GRPClient()
        payload = None
        http_status = None
        error = None
        try:
            payload = await client.get_taxpayer(unp)
            http_status = 200
        except Exception as e:
            # Best-effort error capture; we still store last_error in DB
            error = str(e)
        finally:
            await client.close()

        crud.upsert_from_api(unp=unp, payload=payload if isinstance(payload, dict) else None, http_status=http_status, error=error)
        db.commit()
        record = crud.get_by_unp(unp)

    if record is None:
        raise HTTPException(status_code=404, detail="Данные ГРП не найдены")

    raw_record = crud.get_raw_by_unp(record.unp) if record else None
    return _serialize(record, raw_record=raw_record)


@router.get("/", response_model=list[GrpTaxpayerDataResponse])
async def list_grp_data(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    crud = GrpCRUD(db)
    records = crud.list_recent(limit=limit, offset=offset)
    return [_serialize(r, raw_record=crud.get_raw_by_unp(r.unp)) for r in records]


@router.post("/sync")
async def sync_grp_data(
    only_missing: bool = Query(True, description="Синхронизировать только те УНП, по которым нет данных"),
    limit: int = Query(5000, ge=1, le=200000, description="Сколько УНП обработать за запуск"),
    api_key: str = Depends(verify_api_key),
):
    """Queue background sync for GRP data.

    Requires celery worker + beat to be running. Returns task id.
    """
    try:
        from app.tasks.sync_tasks import sync_grp_for_all  # noqa
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Не удалось импортировать задачу синхронизации: {e}")

    res = sync_grp_for_all.delay(limit=limit, only_missing=only_missing)
    return {"queued": True, "task_id": res.id, "limit": limit, "only_missing": only_missing}


@router.post("/reformat-addresses")
async def reformat_grp_addresses(
    limit: int = Query(10000, ge=1, le=50000, description="Сколько адресов переформатировать за раз"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Переформатировать адреса в существующих записях ГРП.

    Добавляет пробелы после сокращений (г., ул., кв.) для лучшей читаемости.
    """
    crud = GrpCRUD(db)
    updated_count = crud.reformat_addresses(limit=limit)
    return {"updated": updated_count, "limit": limit}
    