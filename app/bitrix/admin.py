"""
Admin panel router for Bitrix24 settings.
"""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bitrix.database import get_db
from app.bitrix.models import AppSettings
from app.bitrix.bitrix_client import BitrixClient, BitrixAPIError

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize Jinja2 templates
templates = Jinja2Templates(directory="app/bitrix/templates")


def _get_auth_token(request: Request) -> str | None:
    """Extract token from request params."""
    params = dict(request.query_params)
    return params.get("PLACEMENT_AUTH_ID") or params.get("AUTH_ID") or params.get("auth")


@router.get("/", response_class=HTMLResponse)
@router.post("/", response_class=HTMLResponse)
async def admin_panel(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Main admin panel page.
    """
    params = dict(request.query_params)
    
    if request.method == "POST":
        try:
            form_data = await request.form()
            params.update(dict(form_data))
        except Exception:
            pass
    
    result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
    app_cfg = result.scalar_one_or_none()
    
    # Update tokens if provided
    auth_id = params.get("AUTH_ID")
    refresh_id = params.get("REFRESH_ID")
    expires_in = int(params.get("AUTH_EXPIRES", 3600))
    
    if auth_id and app_cfg:
        app_cfg.access_token = auth_id
        if refresh_id:
            app_cfg.refresh_token = refresh_id
        app_cfg.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        await db.commit()
    
    presets = []
    userfields = []
    error_message = ""
    success_message = ""
    
    if app_cfg and app_cfg.access_token:
        try:
            bitrix = BitrixClient(db)
            is_admin = await bitrix.is_admin()
            if not is_admin:
                return templates.TemplateResponse(
                    "error.html",
                    {
                        "request": request,
                        "message": "Доступ запрещен. Требуются права администратора."
                    },
                    status_code=403,
                )
            
            presets = await bitrix.get_requisite_presets()
            userfields = await bitrix.get_company_userfields()
        except BitrixAPIError as e:
            logger.error(f"Error loading admin data: {e}")
            error_message = f"Ошибка подключения к Битрикс24: {e}"
    else:
        error_message = "Приложение не установлено. Установите приложение через маркетплейс Битрикс24."
    
    current_preset_id = ""
    if app_cfg and app_cfg.requisite_preset_id:
        current_preset_id = str(app_cfg.requisite_preset_id)
    
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "app_cfg": app_cfg,
            "presets": presets,
            "userfields": userfields,
            "error_message": error_message,
            "success_message": success_message,
            "bitrix_domain": app_cfg.bitrix_domain if app_cfg else "—",
            "current_preset_id": current_preset_id,
            "current_unp_field": app_cfg.unp_field_code if app_cfg else "",
            "current_preset_name": app_cfg.requisite_preset_name if app_cfg else "",
            "current_unp_label": app_cfg.unp_field_label if app_cfg else "",
            "require_admin": app_cfg.require_admin if app_cfg else False,
        },
    )


@router.post("/save", response_class=HTMLResponse)
async def save_settings(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Save settings selected by administrator."""
    form = await request.form()
    preset_id = form.get("preset_id", "")
    preset_name = form.get("preset_name", "")
    unp_field_code = form.get("unp_field_code", "")
    unp_field_label = form.get("unp_field_label", "")
    require_admin = form.get("require_admin") == "true"
    
    # Get auth tokens from query params
    params = dict(request.query_params)
    auth_id = params.get("AUTH_ID")
    refresh_id = params.get("REFRESH_ID")
    expires_in = int(params.get("AUTH_EXPIRES", 3600))
    
    result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
    app_cfg = result.scalar_one_or_none()
    
    if app_cfg is None:
        app_cfg = AppSettings(id=1)
        db.add(app_cfg)
    
    # Update tokens if provided
    if auth_id:
        app_cfg.access_token = auth_id
        if refresh_id:
            app_cfg.refresh_token = refresh_id
        app_cfg.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    
    try:
        bitrix = BitrixClient(db)
        is_admin = await bitrix.is_admin()
        if not is_admin:
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "message": "Доступ запрещён. Требуются права администратора."},
                status_code=403,
            )
    except BitrixAPIError as e:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "message": f"Ошибка проверки прав: {e}"},
            status_code=500,
        )
    
    if preset_id:
        app_cfg.requisite_preset_id = int(preset_id)
        app_cfg.requisite_preset_name = str(preset_name)
    if unp_field_code:
        app_cfg.unp_field_code = str(unp_field_code)
        app_cfg.unp_field_label = str(unp_field_label)
    
    # Save admin requirement setting
    app_cfg.require_admin = require_admin
    
    await db.commit()
    logger.info(f"Settings saved: preset_id={preset_id}, unp_field={unp_field_code}, require_admin={require_admin}")
    
    presets = await BitrixClient(db).get_requisite_presets()
    userfields = await BitrixClient(db).get_company_userfields()
    
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "app_cfg": app_cfg,
            "presets": presets,
            "userfields": userfields,
            "error_message": "",
            "success_message": "✅ Настройки успешно сохранены!",
            "bitrix_domain": app_cfg.bitrix_domain if app_cfg else "—",
            "current_preset_id": str(app_cfg.requisite_preset_id) if app_cfg and app_cfg.requisite_preset_id else "",
            "current_unp_field": app_cfg.unp_field_code if app_cfg else "",
            "current_preset_name": app_cfg.requisite_preset_name if app_cfg else "",
            "current_unp_label": app_cfg.unp_field_label if app_cfg else "",
            "require_admin": app_cfg.require_admin if app_cfg else False,
        },
    )
