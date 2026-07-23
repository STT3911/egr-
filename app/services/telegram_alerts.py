"""Best-effort Telegram alerts for background services."""

from __future__ import annotations

import logging

import requests

from app.core.config import settings

logger = logging.getLogger("egr_aggregator.telegram_alerts")


def telegram_alerts_configured() -> bool:
    return bool(
        settings.PARSER_ALERTS_ENABLED
        and settings.ALERT_TELEGRAM_BOT_TOKEN
        and settings.ALERT_TELEGRAM_CHAT_ID
    )


def send_telegram_alert(text: str) -> bool:
    """Send an operational alert without breaking the calling parser."""
    if not telegram_alerts_configured():
        return False

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{settings.ALERT_TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": settings.ALERT_TELEGRAM_CHAT_ID,
                "text": text[:4096],
                "disable_web_page_preview": True,
            },
            timeout=settings.PARSER_ALERTS_HTTP_TIMEOUT_SECONDS,
        )
        if not response.ok:
            logger.warning(
                "Telegram alert failed: HTTP %s %s",
                response.status_code,
                response.text[:300],
            )
            return False
        return True
    except Exception as exc:
        safe_error = str(exc).replace(
            str(settings.ALERT_TELEGRAM_BOT_TOKEN),
            "***",
        )
        logger.warning("Telegram alert failed: %s: %s", type(exc).__name__, safe_error)
        return False
