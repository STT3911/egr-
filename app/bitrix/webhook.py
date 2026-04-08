"""
Webhook handler for OnCrmCompanyUpdate event.
"""

import logging
from typing import Any

from app.bitrix.bitrix_client import BitrixClient
from app.bitrix.egr_client import EGRClient
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select  # ИСПРАВЛЕНИЕ: Добавлен импорт select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bitrix.database import AsyncSessionLocal, get_db
from app.bitrix.models import AppSettings
from app.bitrix.requisite_service import RequisiteService

logger = logging.getLogger(__name__)
router = APIRouter()

def _normalize_payload(data: dict | None) -> dict[str, Any]:
    """Normalize Bitrix form-data payloads that use bracket notation."""
    normalized: dict[str, Any] = {}
    if not data:
        return normalized
    
    for raw_key, value in data.items():
        if not isinstance(raw_key, str) or "[" not in raw_key:
            normalized[raw_key] = value
            continue
        
        parts = raw_key.replace("]", "").split("[")
        current = normalized
        for part in parts[:-1]:
            nested = current.get(part)
            if not isinstance(nested, dict):
                nested = {}
                current[part] = nested
            current = nested
        current[parts[-1]] = value
    
    return normalized

def _extract_company_id(payload: dict) -> str:
    """Extract company ID from webhook payload."""
    data = payload.get("data", {})
    if isinstance(data, dict):
        fields = data.get("FIELDS", {})
        if isinstance(fields, dict) and fields.get("ID"):
            return str(fields["ID"])
    
    fields = payload.get("FIELDS", {})
    if isinstance(fields, dict) and fields.get("ID"):
        return str(fields["ID"])
    
    return str(payload.get("ID", "") or "")

async def _validate_webhook_source(db: AsyncSession, payload: dict) -> bool:
    """
    Validate webhook source against stored settings.
    Returns: bool (is_valid)
    """
    # Ищем настройки. В идеале искать по member_id, но пока оставим limit(1)
    result = await db.execute(select(AppSettings).limit(1))
    app_cfg = result.scalar_one_or_none()
    
    if app_cfg is None:
        logger.warning("Webhook validation failed: App settings not found in DB.")
        return False
    
    auth = payload.get("auth", {})
    if not isinstance(auth, dict):
        auth = {}
    
    incoming_domain = (
        auth.get("domain") or auth.get("DOMAIN")
        or payload.get("DOMAIN") or payload.get("auth[domain]")
    )
    incoming_member_id = (
        auth.get("member_id") or auth.get("MEMBER_ID")
        or payload.get("member_id") or payload.get("MEMBER_ID")
        or auth.get("auth[member_id]")
    )
    
    if app_cfg.bitrix_domain and incoming_domain and str(incoming_domain) != app_cfg.bitrix_domain:
        logger.warning(f"Webhook rejected: domain mismatch ({incoming_domain} != {app_cfg.bitrix_domain}).")
        return False
    
    if app_cfg.bitrix_member_id and incoming_member_id and str(incoming_member_id) != app_cfg.bitrix_member_id:
        logger.warning(f"Webhook rejected: member_id mismatch ({incoming_member_id} != {app_cfg.bitrix_member_id}).")
        return False
        
    
    return True

async def _process_company_update_task(company_id: int) -> None:
    """Background task to process company update."""
    async with AsyncSessionLocal() as db:
        bitrix_client = BitrixClient(db)
        egr_client = EGRClient()
        service = RequisiteService(bitrix_client, egr_client)
        await service.process_company_update(company_id)

        
@router.post("/company-update")
async def company_update_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Handler for OnCrmCompanyUpdate event.
    Extracts company ID and runs processing in background.
    """
    try:
        content_type = request.headers.get("content-type", "")
        
        if "application/json" in content_type:
            raw_body = await request.json()
        else:
            form = await request.form()
            raw_body = dict(form)
        
        body = _normalize_payload(raw_body if isinstance(raw_body, dict) else {})
        
        # Проверяем источник вебхука (домен и member_id)
        is_valid = await _validate_webhook_source(db, body)
        if not is_valid:
            return JSONResponse(
                {"status": "error", "message": "Webhook source validation failed"},
                status_code=403,
            )
        
        company_id_str = _extract_company_id(body)
        if not company_id_str:
            logger.warning(f"Webhook: Company ID not found in payload: {body}")
            return JSONResponse({"status": "error", "message": "Company ID not found"}, status_code=400)
        
        company_id = int(company_id_str)
        logger.info(f"Webhook: Received OnCrmCompanyUpdate for company ID={company_id}")
        
        # Отправляем в фон, чтобы Битрикс быстро получил ответ 200 OK
        background_tasks.add_task(_process_company_update_task, company_id)
        return JSONResponse({"status": "ok"})
    
    except ValueError as e:
        logger.error(f"Webhook: parsing error: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)
    except Exception as e:
        logger.error(f"Webhook: unexpected error: {e}", exc_info=True)
        return JSONResponse({"status": "error", "message": "Internal error"}, status_code=500)