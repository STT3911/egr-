"""
Router for Bitrix24 app installation.
"""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.bitrix.database import get_db
from app.bitrix.models import AppSettings

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize Jinja2 templates
templates = Jinja2Templates(directory="app/bitrix/templates")


@router.get("/install", response_class=HTMLResponse)
@router.post("/install", response_class=HTMLResponse)
async def install_app(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Handler for app installation from Bitrix24 marketplace.
    
    Bitrix24 sends:
      - DOMAIN - portal domain
      - AUTH_ID - access token
      - REFRESH_ID - refresh token
      - AUTH_EXPIRES - token lifetime in seconds
      - member_id, APP_SID and other params
    """
    params = dict(request.query_params)
    
    if request.method == "POST":
        try:
            body = await request.form()
            params.update(dict(body))
        except Exception:
            pass
    
    domain = params.get("DOMAIN", "")
    member_id = params.get("member_id") or params.get("MEMBER_ID", "")
    access_token = params.get("AUTH_ID", "")
    refresh_token = params.get("REFRESH_ID", "")
    expires_in = int(params.get("AUTH_EXPIRES", 3600))
    
    if not domain or not access_token:
        logger.error(f"Installation: required params missing. Params: {params}")
        return templates.TemplateResponse(
            "install.html",
            {
                "request": request,
                "error": "Ошибка установки: отсутствуют параметры авторизации.",
                "domain": ""
            },
            status_code=400
        )
    
    # Save tokens to DB
    result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
    app_cfg = result.scalar_one_or_none()
    
    if app_cfg is None:
        app_cfg = AppSettings(id=1)
        db.add(app_cfg)
    
    app_cfg.bitrix_domain = domain
    app_cfg.bitrix_member_id = member_id or app_cfg.bitrix_member_id
    app_cfg.access_token = access_token
    app_cfg.refresh_token = refresh_token
    app_cfg.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    await db.commit()
    
    logger.info(f"App installed for domain: {domain}")
    
    return templates.TemplateResponse(
        "install.html",
        {
            "request": request,
            "error": None,
            "domain": domain
        }
    )
