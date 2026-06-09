"""
Эмиссия событий по подпискам на компании.

Когда при обработке данных у компании происходит изменение, на которое
кто-то подписан, сюда складывается запись в таблицу subscription_events
(очередь). Доставку/рассылку этих записей сделаем отдельно (пулинг).

Важно по производительности: при массовой обработке (сотни тысяч компаний)
большинство UNP никто не отслеживает. Поэтому держим в памяти короткоживущий
кэш множества подписанных UNP — для неотслеживаемой компании всё сводится к
проверке принадлежности множеству, без запроса в БД.
"""
import time
import logging
from datetime import datetime

from app.database.models import CompanySubscription, SubscriptionEvent

logger = logging.getLogger(__name__)

# --- Каталог типов событий (согласован с заказчиком) ---------------------
EVENT_STATUS_CHANGED = "status_changed"          # смена статуса
EVENT_LIQUIDATION = "liquidation_started"        # начата ликвидация/реорганизация
EVENT_BANKRUPTCY = "bankruptcy"                  # дело о банкротстве появилось/изменилось
EVENT_LOCKED_SUPPLIER = "locked_supplier"        # реестр недобросовестных поставщиков
EVENT_TAX_DEBT = "tax_debt"                      # налоговая задолженность (МНС)
EVENT_NAME_CHANGED = "name_changed"              # смена наименования
EVENT_ADDRESS_CHANGED = "address_changed"        # смена юр. адреса
EVENT_DIRECTOR_CHANGED = "director_changed"      # смена руководителя/учредителей
EVENT_LICENSE_CHANGED = "license_changed"        # лицензия выдана/отозвана
EVENT_VED_CHANGED = "ved_changed"                # изменение видов деятельности
EVENT_REGISTRY_APPEARANCE = "registry_appearance"  # появление в реестрах МАРТ/ПВТ/ЕАЭС
EVENT_NEW_REGISTRATION = "new_registration"      # новая регистрация

ALL_EVENT_TYPES = {
    EVENT_STATUS_CHANGED, EVENT_LIQUIDATION, EVENT_BANKRUPTCY, EVENT_LOCKED_SUPPLIER,
    EVENT_TAX_DEBT, EVENT_NAME_CHANGED, EVENT_ADDRESS_CHANGED, EVENT_DIRECTOR_CHANGED,
    EVENT_LICENSE_CHANGED, EVENT_VED_CHANGED, EVENT_REGISTRY_APPEARANCE, EVENT_NEW_REGISTRATION,
}

# Кэш подписанных UNP (на процесс), TTL в секундах
_CACHE_TTL = 30
_cache = {"unps": frozenset(), "ts": 0.0}


def _subscribed_unps(db) -> frozenset:
    now = time.time()
    if now - _cache["ts"] > _CACHE_TTL:
        try:
            rows = db.query(CompanySubscription.unp).distinct().all()
            _cache["unps"] = frozenset(r[0] for r in rows)
            _cache["ts"] = now
        except Exception as e:  # таблицы ещё нет / БД недоступна — не валим обработку
            logger.warning("subscription cache refresh failed: %s", e)
            _cache["ts"] = now  # не долбим БД каждую строку
    return _cache["unps"]


def _as_text(value) -> str | None:
    if value is None:
        return None
    return str(value)


def emit_company_event(db, unp, event_type: str, old_value=None, new_value=None) -> int:
    """
    Поставить событие в очередь для всех подписчиков этой компании,
    у кого event_type попадает в их подписку (пустой список event_types = все).

    old_value / new_value — значения "было / стало" (приводятся к тексту).
    НЕ коммитит — записи добавляются в текущую сессию, коммит делает вызывающий код.
    Возвращает число созданных записей.
    """
    try:
        unp_int = int(unp)
    except (TypeError, ValueError):
        return 0

    # Быстрый путь: компанию никто не отслеживает — выходим без запроса в БД.
    if unp_int not in _subscribed_unps(db):
        return 0

    subs = (
        db.query(CompanySubscription)
        .filter(CompanySubscription.unp == unp_int)
        .all()
    )
    created = 0
    for s in subs:
        types = s.event_types or []
        if types and event_type not in types:
            continue
        db.add(SubscriptionEvent(
            user_id=s.user_id,
            unp=unp_int,
            event_type=event_type,
            old_value=_as_text(old_value),
            new_value=_as_text(new_value),
            occurred_at=datetime.now(),
        ))
        created += 1
    if created:
        logger.info("subscription event %s for UNP %s → %s records", event_type, unp_int, created)
    return created
