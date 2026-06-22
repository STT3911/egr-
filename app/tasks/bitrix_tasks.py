"""
Keep-alive Битрикс-токенов.

Раз в сутки beat принудительно дёргает `app.info`. Это триггерит наш
авто-refresh: access_token (живёт ~1ч) к моменту вызова уже истёк, поэтому
обновляется через refresh_token, а Битрикс отдаёт новый refresh_token —
тем самым 30-дневный срок refresh_token сбрасывается. Без этого при долгом
простое (нет вебхуков) refresh_token протухает и приложение требует переустановки.

Пользователь для работы не нужен — всё под сохранённым install-токеном.
При сбое — лог ERROR + (если настроено) телеграм-алерт, чтобы протухание
не прошло молча.
"""
import asyncio
import logging

import requests

from app.core.config import settings
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _send_alert(text: str) -> None:
    """Best-effort алерт в Telegram. Если токен/чат не заданы — тихо пропускаем."""
    token = settings.ALERT_TELEGRAM_BOT_TOKEN
    chat_id = settings.ALERT_TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text[:4096], "disable_web_page_preview": True},
            timeout=8,
        )
    except Exception as ex:
        logger.warning("keepalive alert send failed: %s", ex)


async def _keepalive() -> object:
    # Импорт внутри — у Битрикса своя async-сессия и клиент, не тянем их в воркер без нужды.
    from app.bitrix.bitrix_client import BitrixClient
    from app.bitrix.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        client = BitrixClient(db)
        return await client.call("app.info")


@celery_app.task(name="app.tasks.bitrix_tasks.bitrix_token_keepalive")
def bitrix_token_keepalive():
    """Принудительный keep-alive токена Битрикса (раз в сутки)."""
    try:
        result = asyncio.run(_keepalive())
        app_code = result.get("CODE") if isinstance(result, dict) else None
        logger.info("bitrix keepalive ok (app=%s)", app_code)
        return {"ok": True}
    except Exception as ex:
        logger.error("bitrix keepalive FAILED: %s", ex, exc_info=True)
        _send_alert(
            f"⚠️ Bitrix keep-alive не смог обновить токен: {ex}\n"
            f"Refresh_token может протухнуть — проверьте интеграцию (возможно, нужна переустановка приложения)."
        )
        return {"ok": False, "error": str(ex)}
