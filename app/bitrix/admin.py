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
from app.bitrix.tenancy import find_settings, next_settings_id
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


@router.api_route("/", methods=["GET", "POST"], response_class=HTMLResponse)
async def admin_panel(request: Request, db: AsyncSession = Depends(get_db)):
    # 1. Собираем параметры из URL и тела POST-запроса
    params = dict(request.query_params)
    if request.method == "POST":
        try:
            form_data = await request.form()
            params.update(dict(form_data))
        except Exception as e:
            logger.error(f"Error reading form data: {e}")

    # 2. Ищем данные авторизации
    domain = params.get("DOMAIN") or params.get("domain")
    auth_id = (params.get("AUTH_ID") or params.get("auth") or "").strip()
    refresh_id = (params.get("REFRESH_ID") or params.get("refresh_id") or "").strip()
    expires_raw = params.get("AUTH_EXPIRES") or params.get("expires", 3600)
    try:
        expires_in = int(expires_raw)
    except (TypeError, ValueError):
        expires_in = 3600
    member_id = params.get("member_id") or params.get("MEMBER_ID")

    if not domain or not auth_id:
        logger.warning(f"Auth failed. Params found: {list(params.keys())}")
        return templates.TemplateResponse(
            "error.html", 
            {"request": request, "message": "Ошибка: Не получены данные авторизации от Битрикс24."}, 
            status_code=400
        )

    # 3. Проверка прав администратора
    is_admin = await _check_is_admin_on_the_fly(domain, auth_id)
    if not is_admin:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "message": "Доступ запрещен. Требуются права администратора портала."},
            status_code=403,
        )

    # 4. Обновление токенов в БД — по порталу (member_id, резерв домен), мультитенант.
    app_cfg = await find_settings(db, member_id=member_id, domain=domain)

    if not app_cfg:
        app_cfg = AppSettings(id=await next_settings_id(db))
        db.add(app_cfg)

    if member_id:
        app_cfg.bitrix_member_id = member_id
    app_cfg.access_token = auth_id
    if refresh_id:
        app_cfg.refresh_token = refresh_id
    app_cfg.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    
    await db.commit()

    # 5. Загрузка данных для списков
    presets = []
    userfields = []
    error_message = ""
    
    try:
        bitrix = BitrixClient(db, domain=domain)
        presets = await bitrix.get_requisite_presets()
        userfields = await bitrix.get_company_userfields()
        
        # Исправляем пустые строки: добавляем NICE_NAME
        for f in userfields:
            base_name = f.get('FIELD_NAME', 'Неизвестное поле')
            nice_name = ""
            for key in ['EDIT_FORM_LABEL', 'LIST_COLUMN_LABEL', 'LIST_FILTER_LABEL']:
                val = f.get(key)
                if isinstance(val, dict) and val.get('ru'):
                    nice_name = val['ru']
                    break
                elif isinstance(val, str) and val.strip():
                    nice_name = val.strip()
                    break
            # Если имени нет, показываем системный код
            f['NICE_NAME'] = nice_name if nice_name else base_name
            
    except BitrixAPIError as e:
        logger.error(f"Error loading admin data: {e}")
        error_message = f"Ошибка подключения к API: {e}"

    # Передаем current_preset_id и current_unp_field, чтобы форма не сбрасывалась
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "app_cfg": app_cfg,
            "presets": presets,
            "userfields": userfields,
            "current_preset_id": str(app_cfg.requisite_preset_id) if app_cfg and app_cfg.requisite_preset_id else "",
            "current_unp_field": app_cfg.unp_field_code if app_cfg else "",
            "error_message": error_message,
            "success_message": "",
            "domain": domain,
            "auth_id": auth_id,
            "refresh_id": refresh_id,
        },
    )

@router.post("/create-unp-field", response_class=HTMLResponse)
async def create_unp_field(request: Request, db: AsyncSession = Depends(get_db)):
    """Handler for 'Create UNP Field' button."""
    form = await request.form() 
    domain = form.get("DOMAIN")
    auth_id = form.get("AUTH_ID")

    if not await _check_is_admin_on_the_fly(domain, auth_id):
        return HTMLResponse("Forbidden", status_code=403)

    bitrix = BitrixClient(db, domain=domain)
    try:
        await bitrix.create_unp_userfield()
    except Exception as e:
        logger.error(f"Field creation info: {e}")

    # После создания возвращаем обычную админку
    return await admin_panel(request, db)


@router.post("/save", response_class=HTMLResponse)
async def save_settings(request: Request, db: AsyncSession = Depends(get_db)):
    """Save settings selected by administrator."""
    form = await request.form()
    
    domain = form.get("DOMAIN")
    auth_id = form.get("AUTH_ID")
    
    preset_id = form.get("preset_id", "")
    unp_field_code = form.get("unp_field_code", "")
    ip_mask_full = form.get("ip_mask_full", "Индивидуальный предприниматель {company_name}")
    ip_mask_short = form.get("ip_mask_short", "ИП {company_name}")
    ip_mask_basis = form.get("ip_mask_basis", "Свидетельство о регистрации № {company_unp}")

    if not await _check_is_admin_on_the_fly(domain, auth_id):
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "message": "Сессия истекла или нет прав администратора."},
            status_code=403,
        )

    # Ищем настройки конкретно для этого домена
    result = await db.execute(select(AppSettings).filter(AppSettings.bitrix_domain == domain).limit(1))
    app_cfg = result.scalar_one_or_none()
    
    if app_cfg is None:
        return templates.TemplateResponse("error.html", {"request": request, "message": "Ошибка: Приложение не инициализировано."}, status_code=500)

    # Сохраняем настройки
    if preset_id:
        app_cfg.requisite_preset_id = int(preset_id)
    if unp_field_code:
        app_cfg.unp_field_code = str(unp_field_code)
        
    app_cfg.ip_mask_full = str(ip_mask_full)
    app_cfg.ip_mask_short = str(ip_mask_short)
    app_cfg.ip_mask_basis = str(ip_mask_basis)

    await db.commit()
    logger.info(f"Settings saved successfully for {domain}")

    # Самовосстановление подписки: гарантируем, что обработчик ONCRMCOMPANYUPDATE
    # зарегистрирован, даже если Битрикс не вызвал установочный путь /bitrix/install.
    try:
        from app.bitrix.install import _bind_company_update_event
        await _bind_company_update_event(domain, auth_id)
    except Exception as e:
        logger.error(f"Failed to ensure event subscription on save: {e}")

    # Загружаем списки заново для отображения успешной страницы
    presets, userfields = [], []
    try:
        bitrix = BitrixClient(db, domain=domain)
        presets = await bitrix.get_requisite_presets()
        userfields = await bitrix.get_company_userfields()
        
        # Точно так же добавляем NICE_NAME, чтобы списки не сломались после сохранения
        for f in userfields:
            base_name = f.get('FIELD_NAME', 'Неизвестное поле')
            nice_name = ""
            for key in ['EDIT_FORM_LABEL', 'LIST_COLUMN_LABEL', 'LIST_FILTER_LABEL']:
                val = f.get(key)
                if isinstance(val, dict) and val.get('ru'):
                    nice_name = val['ru']
                    break
                elif isinstance(val, str) and val.strip():
                    nice_name = val.strip()
                    break
            f['NICE_NAME'] = nice_name if nice_name else base_name
    except:
        pass

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "app_cfg": app_cfg,
            "presets": presets,
            "userfields": userfields,
            "current_preset_id": str(app_cfg.requisite_preset_id) if app_cfg.requisite_preset_id else "",
            "current_unp_field": app_cfg.unp_field_code,
            "success_message": "✅ Настройки успешно сохранены!",
            "error_message": "",
            "domain": domain,
            "auth_id": auth_id,
        },
    )