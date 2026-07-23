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

from app.services.telegram_alerts import send_telegram_alert
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _keepalive_all() -> list[dict]:
    # Импорт внутри — у Битрикса своя async-сессия и клиент, не тянем их в воркер без нужды.
    from sqlalchemy import select

    from app.bitrix.bitrix_client import BitrixClient
    from app.bitrix.database import AsyncSessionLocal
    from app.bitrix.models import AppSettings

    results: list[dict] = []
    async with AsyncSessionLocal() as db:
        portals = (await db.execute(select(AppSettings))).scalars().all()
        # По каждому установленному порталу — отдельно (мультитенант): у каждого свой токен.
        for cfg in portals:
            client = BitrixClient(db, domain=cfg.bitrix_domain, member_id=cfg.bitrix_member_id)
            try:
                await client.call("app.info")
                results.append({"member_id": cfg.bitrix_member_id, "domain": cfg.bitrix_domain, "ok": True})
            except Exception as ex:
                logger.error("keepalive failed for portal %s (%s): %s", cfg.bitrix_domain, cfg.bitrix_member_id, ex)
                results.append({"member_id": cfg.bitrix_member_id, "domain": cfg.bitrix_domain,
                                "ok": False, "error": str(ex)})
    return results


@celery_app.task(name="app.tasks.bitrix_tasks.bitrix_token_keepalive")
def bitrix_token_keepalive():
    """Принудительный keep-alive токенов Битрикса по всем порталам (раз в сутки)."""
    try:
        results = asyncio.run(_keepalive_all())
    except Exception as ex:
        logger.error("bitrix keepalive FAILED (run): %s", ex, exc_info=True)
        send_telegram_alert(f"⚠️ Bitrix keep-alive упал целиком: {ex}")
        return {"ok": False, "error": str(ex)}

    failed = [r for r in results if not r["ok"]]
    logger.info("bitrix keepalive: %d portal(s), %d failed", len(results), len(failed))
    if failed:
        lines = "\n".join(f"• {r['domain'] or r['member_id']}: {r.get('error')}" for r in failed)
        send_telegram_alert(
            "⚠️ Bitrix keep-alive не смог обновить токен по порталам:\n"
            f"{lines}\nRefresh_token может протухнуть — проверьте интеграцию (возможно, нужна переустановка)."
        )
    return {"ok": not failed, "portals": len(results), "failed": len(failed)}
