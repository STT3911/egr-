"""
Push-доставка событий подписок на webhook клиента ("адрес клиента").

Раз в ~60с beat запускает deliver_subscription_events:
  • берём пользователей с заданным webhook_url и необработанными событиями;
  • шлём пачкой POST на их URL с подписью X-EGR-Signature (HMAC по webhook_secret);
  • 2xx → проставляем processed_at (доставлено);
  • ошибка → delivery_attempts++ и last_delivery_error, ретрай на следующем тике
    (после MAX_ATTEMPTS событие перестаёт ретраиться — «дед-леттер», можно сбросить вручную).
"""
import json
import logging
from datetime import datetime
from html import escape

import requests

from app.core.config import settings
from app.core.database import SessionLocal
from app.database.models import User, SubscriptionEvent
from app.services.auth import sign_payload
from app.services.company_names import get_company_names
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 10
BATCH_PER_USER = 100
HTTP_TIMEOUT = 8

_EVENT_LABELS = {
    "status_changed": "Изменение статуса",
    "liquidation_started": "Начата ликвидация/реорганизация",
    "name_changed": "Изменение наименования",
    "address_changed": "Изменение адреса",
    "director_changed": "Изменение руководителя/учредителей",
    "ved_changed": "Изменение видов деятельности",
    "new_registration": "Новая регистрация",
}

# События ядра ЕГР (госреестр юрлиц/ИП). Для остальных источник — отдельный реестр.
_EGR_EVENTS = set(_EVENT_LABELS)

# Заголовок по источнику (реестру) для событий вне ЕГР.
_EVENT_SOURCE_TITLE = {
    "license_changed": "📜 Реестр лицензий (license.gov.by)",
    "locked_supplier": "⛔ Реестр недобросовестных поставщиков (МАРТ)",
    "bankruptcy": "⚖️ Реестр дел о банкротстве (bankrot.gov.by)",
    "tax_debt": "💰 Налоговая задолженность (МНС)",
    "registry_appearance": "🏛 Реестры МАРТ/ПВТ/ЕАЭС",
}


def _format_event_telegram(
    e: SubscriptionEvent,
    company_name: str | None = None,
) -> str:
    is_egr = e.event_type in _EGR_EVENTS
    if is_egr:
        title = "📋 Изменение в ЕГР"
    else:
        title = _EVENT_SOURCE_TITLE.get(e.event_type, "🔔 Изменение")
    lines = [f"<b>{title}</b>"]
    if company_name:
        lines.append(f"<b>{escape(company_name[:300])}</b>")
    lines.append(f"УНП: <code>{e.unp}</code>")
    # Для ЕГР заголовок общий — уточняем что именно изменилось.
    if is_egr:
        lines.append(f"Событие: {_EVENT_LABELS[e.event_type]}")
    if e.old_value:
        lines.append(f"Было: {escape(str(e.old_value)[:300])}")
    if e.new_value:
        lines.append(f"Стало: {escape(str(e.new_value)[:300])}")
    app_url = (settings.APP_URL or "").rstrip("/")
    if app_url:
        company_url = f"{app_url}/company/{e.unp}"
        lines.append(
            f'<a href="{escape(company_url, quote=True)}">Открыть карточку компании</a>'
        )
    return "\n".join(lines)


def _event_dict(e: SubscriptionEvent) -> dict:
    return {
        "id": e.id,
        "unp": e.unp,
        "event_type": e.event_type,
        "old_value": e.old_value,
        "new_value": e.new_value,
        "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
    }


def _mark_fully_processed(db, event_ids: list[int]) -> None:
    """Проставить processed_at событиям, доставленным во все настроенные у юзера каналы.

    Канал считается «закрытым», если он доставлен (delivered_at не пуст),
    исчерпал попытки (attempts >= MAX_ATTEMPTS) или не настроен у пользователя.
    """
    if not event_ids:
        return
    rows = (
        db.query(SubscriptionEvent, User)
        .join(User, User.id == SubscriptionEvent.user_id)
        .filter(SubscriptionEvent.id.in_(event_ids),
                SubscriptionEvent.processed_at.is_(None))
        .all()
    )
    now = datetime.now()
    for e, user in rows:
        wh_needed = bool(user.webhook_url)
        tg_needed = bool(user.telegram_id)
        wh_done = (not wh_needed) or e.webhook_delivered_at is not None or e.webhook_attempts >= MAX_ATTEMPTS
        tg_done = (not tg_needed) or e.telegram_delivered_at is not None or e.telegram_attempts >= MAX_ATTEMPTS
        if wh_done and tg_done:
            e.processed_at = now


@celery_app.task
def deliver_subscription_events():
    db = SessionLocal()
    delivered = 0
    try:
        user_ids = [
            r[0]
            for r in db.query(SubscriptionEvent.user_id)
            .join(User, User.id == SubscriptionEvent.user_id)
            .filter(
                SubscriptionEvent.webhook_delivered_at.is_(None),
                SubscriptionEvent.webhook_attempts < MAX_ATTEMPTS,
                User.webhook_url.isnot(None),
            )
            .distinct()
            .all()
        ]

        for uid in user_ids:
            user = db.get(User, uid)
            if not user or not user.webhook_url:
                continue

            events = (
                db.query(SubscriptionEvent)
                .filter(
                    SubscriptionEvent.user_id == uid,
                    SubscriptionEvent.webhook_delivered_at.is_(None),
                    SubscriptionEvent.webhook_attempts < MAX_ATTEMPTS,
                )
                .order_by(SubscriptionEvent.id.asc())
                .limit(BATCH_PER_USER)
                .all()
            )
            if not events:
                continue

            payload = {"events": [_event_dict(e) for e in events]}
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            if user.webhook_secret:
                headers["X-EGR-Signature"] = sign_payload(user.webhook_secret, body)

            try:
                resp = requests.post(user.webhook_url, data=body, headers=headers, timeout=HTTP_TIMEOUT)
                if 200 <= resp.status_code < 300:
                    now = datetime.now()
                    for e in events:
                        e.webhook_delivered_at = now
                    delivered += len(events)
                    logger.info("webhook delivered %s events to user %s", len(events), uid)
                else:
                    for e in events:
                        e.webhook_attempts += 1
                        e.webhook_error = f"http {resp.status_code}"
                    logger.warning("webhook user %s → http %s", uid, resp.status_code)
            except Exception as ex:
                for e in events:
                    e.webhook_attempts += 1
                    e.webhook_error = str(ex)[:300]
                logger.warning("webhook user %s failed: %s", uid, ex)

            _mark_fully_processed(db, [e.id for e in events])
            db.commit()

        return delivered
    finally:
        db.close()


@celery_app.task
def deliver_telegram_events():
    """Доставка событий подписок в Telegram (пользователи с заданным telegram_id)."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return 0

    tg_url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    db = SessionLocal()
    delivered = 0
    try:
        user_ids = [
            r[0]
            for r in db.query(SubscriptionEvent.user_id)
            .join(User, User.id == SubscriptionEvent.user_id)
            .filter(
                SubscriptionEvent.telegram_delivered_at.is_(None),
                SubscriptionEvent.telegram_attempts < MAX_ATTEMPTS,
                User.telegram_id.isnot(None),
            )
            .distinct()
            .all()
        ]

        for uid in user_ids:
            user = db.get(User, uid)
            if not user or not user.telegram_id:
                continue

            events = (
                db.query(SubscriptionEvent)
                .filter(
                    SubscriptionEvent.user_id == uid,
                    SubscriptionEvent.telegram_delivered_at.is_(None),
                    SubscriptionEvent.telegram_attempts < MAX_ATTEMPTS,
                )
                .order_by(SubscriptionEvent.id.asc())
                .limit(BATCH_PER_USER)
                .all()
            )
            if not events:
                continue

            company_names = get_company_names(db, {event.unp for event in events})
            now = datetime.now()
            for event in events:
                text = _format_event_telegram(
                    event,
                    company_names.get(event.unp),
                )
                try:
                    resp = requests.post(
                        tg_url,
                        json={
                            "chat_id": user.telegram_id,
                            "text": text[:4096],
                            "parse_mode": "HTML",
                            "disable_web_page_preview": True,
                        },
                        timeout=HTTP_TIMEOUT,
                    )
                    if 200 <= resp.status_code < 300:
                        event.telegram_delivered_at = now
                        delivered += 1
                        logger.info("telegram: delivered event %s to user %s", event.id, uid)
                    else:
                        event.telegram_attempts += 1
                        event.telegram_error = f"http {resp.status_code}: {resp.text[:200]}"
                        logger.warning("telegram: user %s event %s → http %s", uid, event.id, resp.status_code)
                        if resp.status_code == 429:
                            break
                except Exception as ex:
                    event.telegram_attempts += 1
                    event.telegram_error = str(ex)[:300]
                    logger.warning("telegram: user %s event %s failed: %s", uid, event.id, ex)

            _mark_fully_processed(db, [e.id for e in events])
            db.commit()

        return delivered
    finally:
        db.close()
