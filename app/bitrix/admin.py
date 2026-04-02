"""
Admin panel router for Bitrix24 settings.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
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

templates = Jinja2Templates(directory="app/bitrix/templates")


async def _check_is_admin_on_the_fly(domain: str, auth_id: str) -> bool:
    """Fast check if the current user is an admin without touching the DB."""
    if not domain or not auth_id:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://{domain}/rest/user.admin.json",
                json={"auth": auth_id}
            )
            return resp.json().get("result", False)
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False


@router.post("/", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_panel(request: Request, db: AsyncSession = Depends(get_db)):
    # 1. Сначала берем всё из URL (Query Params)
    params = dict(request.query_params)
    
    # 2. Если это POST, добавляем данные из формы (тела запроса)
    if request.method == "POST":
        try:
            form_data = await request.form()
            # .update() объединит данные. Если ключи совпадут, форма приоритетнее
            params.update(dict(form_data))
        except Exception as e:
            logger.error(f"Error reading form data: {e}")

    # 3. Ищем данные (учитываем, что Битрикс может прислать AUTH_ID или auth)
    domain = params.get("DOMAIN") or params.get("domain")
    auth_id = params.get("AUTH_ID") or params.get("auth")
    refresh_id = params.get("REFRESH_ID") or params.get("refresh_id")
    # Переводим в int, только если значение есть
    expires_raw = params.get("AUTH_EXPIRES") or params.get("expires", 3600)
    expires_in = int(expires_raw)
    member_id = params.get("member_id") or params.get("MEMBER_ID")

    # Теперь проверка сработает, так как мы "прочесали" и URL, и Form
    if not domain or not auth_id:
        logger.warning(f"Auth failed. Params found: {list(params.keys())}")
        return templates.TemplateResponse(
            "error.html", 
            {"request": request, "message": "Ошибка: Не получены данные авторизации от Битрикс24."}, 
            status_code=400
        )

    # 1. ПРОВЕРЯЕМ ПРАВА ДО ТОГО, КАК ТРОГАТЬ БАЗУ ДАННЫХ
    is_admin = await _check_is_admin_on_the_fly(domain, auth_id)
    if not is_admin:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "message": "Доступ запрещен. Требуются права администратора портала."},
            status_code=403,
        )

    # 2. Теперь безопасно сохраняем настройки и обновляем токены (OAuth)
    result = await db.execute(select(AppSettings).limit(1))
    app_cfg = result.scalar_one_or_none()
    
    if not app_cfg:
        app_cfg = AppSettings()
        db.add(app_cfg)

    app_cfg.bitrix_domain = domain
    if member_id:
        app_cfg.bitrix_member_id = member_id
    app_cfg.access_token = auth_id
    if refresh_id:
        app_cfg.refresh_token = refresh_id
    app_cfg.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    
    await db.commit()

    # 3. Получаем данные для отрисовки формы (пресеты и поля)
    presets = []
    userfields = []
    error_message = ""
    
    try:
        bitrix = BitrixClient(db, domain=domain)
        presets = await bitrix.get_requisite_presets()
        userfields = await bitrix.get_company_userfields()
    except BitrixAPIError as e:
        logger.error(f"Error loading admin data: {e}")
        error_message = f"Ошибка подключения к API: {e}"

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "app_cfg": app_cfg,
            "presets": presets,
            "userfields": userfields,
            "error_message": error_message,
            "success_message": "",
            "domain": domain,
            "auth_id": auth_id, # Передаем в шаблон, чтобы сохранить в скрытых полях формы!
            "refresh_id": refresh_id,
        },
    )


@router.post("/save", response_class=HTMLResponse)
async def save_settings(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Save settings selected by administrator."""
    form = await request.form()
    
    # Извлекаем токены прямо из формы (их нужно добавить как <input type="hidden"> в admin.html)
    domain = form.get("DOMAIN")
    auth_id = form.get("AUTH_ID")
    
    # Извлекаем настройки полей
    preset_id = form.get("preset_id", "")
    preset_name = form.get("preset_name", "")
    unp_field_code = form.get("unp_field_code", "")
    unp_field_label = form.get("unp_field_label", "")
    
    # Извлекаем МАСКИ ДЛЯ ИП (восстановлено из вашего ТЗ)
    ip_mask_full = form.get("ip_mask_full", "Индивидуальный предприниматель {company_name}")
    ip_mask_short = form.get("ip_mask_short", "ИП {company_name}")
    ip_mask_basis = form.get("ip_mask_basis", "Свидетельство о регистрации № {company_unp}")

    # Снова проверяем права (защита от прямой отправки POST-запроса)
    is_admin = await _check_is_admin_on_the_fly(domain, auth_id)
    if not is_admin:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "message": "Сессия истекла или нет прав администратора."},
            status_code=403,
        )

    # Сохраняем в БД
    result = await db.execute(select(AppSettings).limit(1))
    app_cfg = result.scalar_one_or_none()
    
    if app_cfg is None:
        return templates.TemplateResponse("error.html", {"request": request, "message": "Ошибка: Приложение не инициализировано."}, status_code=500)

    if preset_id:
        app_cfg.requisite_preset_id = int(preset_id)
        app_cfg.requisite_preset_name = str(preset_name)
    if unp_field_code:
        app_cfg.unp_field_code = str(unp_field_code)
        app_cfg.unp_field_label = str(unp_field_label)
        
    # Сохраняем маски в БД (убедитесь, что эти колонки добавлены в models.py)
    app_cfg.ip_mask_full = str(ip_mask_full)
    app_cfg.ip_mask_short = str(ip_mask_short)
    app_cfg.ip_mask_basis = str(ip_mask_basis)

    await db.commit()
    logger.info("Settings and IP masks saved successfully.")

    # Перезагружаем списки для рендера успешной страницы
    try:
        bitrix = BitrixClient(db, domain=domain)
        presets = await bitrix.get_requisite_presets()
        userfields = await bitrix.get_company_userfields()
    except:
        presets, userfields = [], []

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "app_cfg": app_cfg,
            "presets": presets,
            "userfields": userfields,
            "success_message": "✅ Настройки и маски ИП успешно сохранены!",
            "error_message": "",
            "domain": domain,
            "auth_id": auth_id,
        },
    )