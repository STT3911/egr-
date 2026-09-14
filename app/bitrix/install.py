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

from app.bitrix.database import get_db
from app.bitrix.models import AppSettings
from app.bitrix.tenancy import find_settings, next_settings_id
from app.core.config import settings
from app.bitrix.security import application_origin, portal_domain

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
    Ensure current handlers, then remove this app's exact obsolete dev handlers.
    Never remove a working handler before its replacement has been registered.
    """
    base = application_origin(settings.APP_URL)
    domain = portal_domain(domain)
    handler_url = f"{base}{WEBHOOK_HANDLER_PATH}"
    rest_url = f"https://{domain}/rest"

    async with httpx.AsyncClient(timeout=30) as client:
        async def call(method, payload):
            response = await client.post(f"{rest_url}/{method}.json", json=payload)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or data.get("error") or "result" not in data:
                code = data.get("error", "invalid_response") if isinstance(data, dict) else "invalid_response"
                # Do not log auth tokens or arbitrary response bodies.
                raise RuntimeError(f"Bitrix24 {method}: {code}")
            return data["result"]

        bindings = await call("event.get", {"auth": access_token})
        if not isinstance(bindings, list) or any(not isinstance(b, dict) for b in bindings):
            raise RuntimeError("Bitrix24 event.get returned an invalid handler list")
        bindings = [b for b in bindings if str(b.get("offline", b.get("OFFLINE", 0))) == "0"]
        for event in COMPANY_EVENTS:
            payload = {"auth": access_token, "event": event, "handler": handler_url}
            current = [b for b in bindings if str(b.get("event", b.get("EVENT", ""))).upper() == event]
            if not any(b.get("handler", b.get("HANDLER")) == handler_url for b in current):
                if await call("event.bind", payload) is not True:
                    raise RuntimeError(f"Bitrix24 event.bind did not confirm {event}")
            logger.info("Subscribed to %s → %s", event, handler_url)

        # event.get is scoped to the token's app. Do NOT clear other paths,
        # portals or production handlers during a dev install.
        if base == "https://company.tenders.by":
            old_handler = f"https://test.tendex.by{WEBHOOK_HANDLER_PATH}"
            for binding in bindings:
                event = str(binding.get("event", binding.get("EVENT", ""))).upper()
                if event in COMPANY_EVENTS and binding.get("handler", binding.get("HANDLER")) == old_handler:
                    payload = {"auth": access_token, "event": event, "handler": old_handler}
                    payload["auth_type"] = binding.get("auth_type", binding.get("AUTH_TYPE")) or 0
                    result = await call("event.unbind", payload)
                    if not isinstance(result, dict) or type(result.get("count")) is not int or result["count"] < 0:
                        raise RuntimeError(f"Bitrix24 event.unbind did not confirm {event}")


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
    
    domain = params.get("DOMAIN") or params.get("domain", "")
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
        logger.error("Installation: required authorization parameters missing")
        return templates.TemplateResponse(
            "install.html",
            {
                "request": request,
                "error": "Ошибка установки: отсутствуют параметры авторизации.",
                "domain": ""
            },
            status_code=400
        )
    
    try:
        domain = portal_domain(domain)
        base = application_origin(settings.APP_URL)
        if request.url.hostname != base.removeprefix("https://"):
            raise ValueError("Домен установки не совпадает с APP_URL этого окружения.")
    except ValueError as exc:
        return templates.TemplateResponse("install.html", {"request": request, "error": str(exc), "domain": domain}, status_code=400)

    from app.bitrix.admin import _check_is_admin_on_the_fly
    if not await _check_is_admin_on_the_fly(domain, access_token):
        return templates.TemplateResponse("install.html", {
            "request": request, "error": "Сессия Б24 истекла или нет прав администратора. Откройте установку из портала заново.", "domain": domain,
        }, status_code=403)

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
    try:
        await _bind_company_events(domain, access_token)
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        logger.error("Bitrix installation event registration failed: %s", type(exc).__name__)
        return templates.TemplateResponse("install.html", {
            "request": request, "domain": domain,
            "error": "Не удалось зарегистрировать обработчики Б24. Установка не завершена. Проверьте права CRM и повторите установку из портала.",
        }, status_code=502)

    logger.info(f"App installed for domain: {domain}")
    
    return templates.TemplateResponse(
        "install.html",
        {
            "request": request,
            "error": None,
            "domain": domain
        }
    )
