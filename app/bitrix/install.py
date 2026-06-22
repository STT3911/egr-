"""
Router for Bitrix24 app installation.
"""

import logging
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.bitrix.database import get_db
from app.bitrix.models import AppSettings
from app.bitrix.tenancy import find_settings, next_settings_id
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize Jinja2 templates
templates = Jinja2Templates(directory="app/bitrix/templates")

# События, на которые подписывается приложение, и относительный путь обработчика.
# Реквизиты заполняем и при СОЗДАНИИ компании, и при её изменении.
COMPANY_EVENTS = ("ONCRMCOMPANYADD", "ONCRMCOMPANYUPDATE")
WEBHOOK_HANDLER_PATH = "/bitrix/webhook/company-update"


async def _bind_company_events(domain: str, access_token: str) -> None:
    """
    Подписать приложение на события создания и изменения компании.

    Без этого Битрикс не будет дёргать наш webhook — вся событийная модель
    держится на этих подписках. Перед bind делаем unbind, чтобы повторная
    установка не плодила дубли обработчиков.
    """
    base = (settings.APP_URL or "").rstrip("/")
    if not base:
        logger.error(
            "APP_URL не задан — невозможно зарегистрировать handler событий %s. "
            "Webhook не будет вызываться.", ", ".join(COMPANY_EVENTS),
        )
        return

    handler_url = f"{base}{WEBHOOK_HANDLER_PATH}"
    rest_url = f"https://{domain}/rest"

    async with httpx.AsyncClient(timeout=30) as client:
        for event in COMPANY_EVENTS:
            payload = {"auth": access_token, "event": event, "handler": handler_url}

            # unbind — best-effort, ошибки игнорируем (подписки могло и не быть).
            try:
                await client.post(f"{rest_url}/event.unbind.json", json=payload)
            except Exception as e:
                logger.info("event.unbind skipped (%s): %s", event, e)

            try:
                resp = await client.post(f"{rest_url}/event.bind.json", json=payload)
                data = resp.json()
                if data.get("error"):
                    logger.error("event.bind failed (%s): %s", event, data)
                else:
                    logger.info("Subscribed to %s → %s", event, handler_url)
            except Exception as e:
                logger.error("event.bind request error (%s): %s", event, e)


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
    access_token = params.get("AUTH_ID", "").strip()
    refresh_token = params.get("REFRESH_ID", "").strip()
    try:
        expires_in = int(params.get("AUTH_EXPIRES") or 3600)
    except (TypeError, ValueError):
        expires_in = 3600

    # Без refresh_token приложение не сможет работать в фоне (нечем обновлять access_token),
    # поэтому требуем оба токена непустыми — иначе не сохраняем мусор и просим переустановить.
    if not domain or not access_token or not refresh_token:
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
    
    # Save tokens to DB — upsert по порталу (member_id), а не в единственную строку id=1.
    # Это и есть мультитенант: установка на второй портал создаёт новую запись,
    # а не затирает токены первого.
    app_cfg = await find_settings(db, member_id=member_id, domain=domain)

    if app_cfg is None:
        app_cfg = AppSettings(id=await next_settings_id(db))
        db.add(app_cfg)

    app_cfg.bitrix_domain = domain
    app_cfg.bitrix_member_id = member_id or app_cfg.bitrix_member_id
    app_cfg.access_token = access_token
    app_cfg.refresh_token = refresh_token
    app_cfg.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    await db.commit()

    # Подписываемся на события создания и изменения компании (иначе webhook не вызовется).
    await _bind_company_events(domain, access_token)

    logger.info(f"App installed for domain: {domain}")
    
    return templates.TemplateResponse(
        "install.html",
        {
            "request": request,
            "error": None,
            "domain": domain
        }
    )
