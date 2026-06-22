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
from app.bitrix.tenancy import find_settings
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

def _extract_auth_ids(payload: dict) -> tuple[str | None, str | None]:
    """Достать domain и member_id отправителя вебхука (разные форматы Битрикса)."""
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
    return (
        str(incoming_domain) if incoming_domain else None,
        str(incoming_member_id) if incoming_member_id else None,
    )

async def _resolve_app_settings(db: AsyncSession, payload: dict):
    """Найти настройки портала-отправителя (мультитенант).

    Возвращает AppSettings нужного портала или None, если портал неизвестен
    (не установлен у нас) — тогда вебхук отклоняем.
    """
    incoming_domain, incoming_member_id = _extract_auth_ids(payload)
    if not incoming_domain and not incoming_member_id:
        logger.warning("Webhook rejected: no domain/member_id in payload.")
        return None

    app_cfg = await find_settings(db, member_id=incoming_member_id, domain=incoming_domain)
    if app_cfg is None:
        logger.warning(
            f"Webhook rejected: unknown portal (member_id={incoming_member_id}, domain={incoming_domain})."
        )
    return app_cfg

async def _process_company_update_task(company_id: int, member_id: str | None, domain: str | None) -> None:
    """Background task to process company update под токеном нужного портала."""
    async with AsyncSessionLocal() as db:
        bitrix_client = BitrixClient(db, domain=domain, member_id=member_id)
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
        
        # Резолвим портал-отправитель (мультитенант). Неизвестный портал → 403.
        app_cfg = await _resolve_app_settings(db, body)
        if app_cfg is None:
            return JSONResponse(
                {"status": "error", "message": "Webhook source validation failed"},
                status_code=403,
            )

        company_id_str = _extract_company_id(body)
        if not company_id_str:
            logger.warning(f"Webhook: Company ID not found in payload: {body}")
            return JSONResponse({"status": "error", "message": "Company ID not found"}, status_code=400)

        company_id = int(company_id_str)
        logger.info(
            f"Webhook: OnCrmCompanyUpdate company ID={company_id} "
            f"(portal member_id={app_cfg.bitrix_member_id}, domain={app_cfg.bitrix_domain})"
        )

        # Отправляем в фон под токеном именно этого портала, чтобы Битрикс быстро получил 200 OK
        background_tasks.add_task(
            _process_company_update_task, company_id, app_cfg.bitrix_member_id, app_cfg.bitrix_domain
        )
        return JSONResponse({"status": "ok"})
    
    except ValueError as e:
        logger.error(f"Webhook: parsing error: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)
    except Exception as e:
        logger.error(f"Webhook: unexpected error: {e}", exc_info=True)
        return JSONResponse({"status": "error", "message": "Internal error"}, status_code=500)
