from datetime import datetime
from types import SimpleNamespace

from app.database.models import CompanySubscription, SubscriptionEvent
from app.services.egr_event_notifications import (
    _source_key,
    emit_egr_source_events,
)
from app.services.subscription_events import ALL_EVENT_TYPES, emit_company_event
from app.tasks import sync_tasks
from app.tasks.webhook_tasks import _format_event_telegram


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)


class _DB:
    def __init__(self, subscriptions, duplicate_user_ids=()):
        self.subscriptions = subscriptions
        self.duplicate_user_ids = duplicate_user_ids
        self.added = []
        self.queries = []

    def query(self, *entities):
        self.queries.append(entities)
        if len(entities) == 1 and entities[0] is CompanySubscription:
            return _Query(self.subscriptions)
        if len(entities) == 1 and entities[0] is SubscriptionEvent.user_id:
            return _Query([(user_id,) for user_id in self.duplicate_user_ids])
        raise AssertionError(f"Unexpected query: {entities!r}")

    def add(self, value):
        self.added.append(value)


def _subscription(user_id, event_types, created_at=None):
    return SimpleNamespace(user_id=user_id, event_types=event_types, created_at=created_at)


def test_emit_company_event_queries_current_subscriptions_without_process_cache():
    db = _DB([_subscription("user-1", [])])

    created = emit_company_event(
        db,
        193712492,
        "status_changed",
        old_value=999,
        new_value=1,
    )

    assert created == 1
    assert len(db.added) == 1
    assert db.added[0].user_id == "user-1"
    assert db.added[0].unp == 193712492
    assert db.added[0].old_value == "999"
    assert db.added[0].new_value == "1"
    assert db.queries[0] == (CompanySubscription,)


def test_emit_company_event_respects_filters_and_deduplication():
    db = _DB(
        [
            _subscription("all-events", []),
            _subscription("bankruptcy-only", ["bankruptcy"]),
            _subscription("duplicate", ["status_changed"]),
        ],
        duplicate_user_ids=["duplicate"],
    )

    created = emit_company_event(db, 193712492, "status_changed", new_value=1)

    assert created == 1
    assert [event.user_id for event in db.added] == ["all-events"]


def test_emit_company_event_skips_database_dedup_query_without_subscribers():
    db = _DB([])

    assert emit_company_event(db, 193712492, "status_changed") == 0
    assert db.added == []
    assert db.queries == [(CompanySubscription,)]


def test_emit_company_event_skips_source_history_before_subscription():
    db = _DB([
        _subscription(
            "user-1",
            [],
            created_at=datetime(2026, 6, 12, 10, 23),
        )
    ])

    created = emit_company_event(
        db,
        193712492,
        "egr_event",
        new_value="Регистрация",
        occurred_at=datetime(2026, 6, 11),
        source_key="egr:193712492:1:v1",
    )

    assert created == 0
    assert db.added == []


def test_emit_company_event_skips_earlier_event_on_subscription_day():
    db = _DB([
        _subscription(
            "user-1",
            [],
            created_at=datetime(2026, 6, 12, 10, 23),
        )
    ])

    created = emit_company_event(
        db,
        193712492,
        "egr_event",
        new_value="Изменение сведений",
        occurred_at=datetime(2026, 6, 12, 0, 0),
        source_key="egr:193712492:2:v1",
    )

    assert created == 0
    assert db.added == []


def test_egr_source_event_has_stable_versioned_key_and_readable_description():
    payload = {
        "NGR04004": 77,
        "dfrom": "2026-08-11",
        "nsi00223": {"vnop": "Принято решение о реорганизации"},
        "vdocn": "42-A",
    }
    db = _DB([_subscription("user-1", [], created_at=datetime(2026, 6, 12))])

    created = emit_egr_source_events(db, 193712492, [payload])

    assert created == 1
    event = db.added[0]
    assert event.event_type == "egr_event"
    assert event.occurred_at == datetime(2026, 8, 11)
    assert "Принято решение о реорганизации" in event.new_value
    assert "42-A" in event.new_value
    assert event.source_key == _source_key(193712492, payload)
    assert _source_key(193712492, payload) == _source_key(193712492, dict(payload))
    assert _source_key(193712492, {**payload, "dto": "2026-08-12"}) != event.source_key


def test_egr_source_event_without_date_is_not_backfilled():
    db = _DB([_subscription("user-1", [])])

    assert emit_egr_source_events(db, 193712492, [{"NGR04004": 77}]) == 0
    assert db.added == []


def test_real_egr_director_event_is_classified_and_uses_minsk_business_date():
    payload = {
        "ngrn": 193712492,
        "dfrom": "2024-08-07T21:00:00.000+00:00",
        "ngr04004": 10398446501,
        "nsi00223": {
            "nkop": 21700,
            "vnop": "Уведомление о назначении (замене) руководителя",
            "nsi00223": 70230,
        },
        # The source currently contains this future document date. Occurrence
        # must be based on dfrom, not ddoc.
        "ddoc": "2029-08-07T21:00:00.000+00:00",
    }
    db = _DB([_subscription("user-1", [], created_at=datetime(2024, 8, 8))])

    assert emit_egr_source_events(db, 193712492, [payload]) == 1
    event = db.added[0]
    assert event.event_type == "director_changed"
    assert event.occurred_at == datetime(2024, 8, 8)
    assert event.source_key.startswith("egr:193712492:10398446501:")
    assert "назначении (замене) руководителя" in event.new_value


def test_egr_event_cancellation_uses_cancellation_date():
    payload = {
        "ngr04004": 10398446501,
        "dfrom": "2024-08-07T21:00:00.000+00:00",
        "dto": "2026-08-11T21:00:00.000+00:00",
        "nsi00223": {"nkop": 21700, "vnop": "Замена руководителя"},
    }
    db = _DB([_subscription("user-1", [], created_at=datetime(2026, 6, 12))])

    assert emit_egr_source_events(db, 193712492, [payload]) == 1
    assert db.added[0].occurred_at == datetime(2026, 8, 12)
    assert "дата отмены" in db.added[0].new_value


def test_telegram_formatter_supports_every_advertised_event_type():
    for event_type in ALL_EVENT_TYPES:
        event = SimpleNamespace(
            unp=193712492,
            event_type=event_type,
            old_value="было",
            new_value="стало",
        )
        message = _format_event_telegram(event, "Тестовая компания")
        assert "193712492" in message
        assert "Тестовая компания" in message


def test_hourly_subscription_refresh_fetches_official_egr_events(monkeypatch):
    raw_row = SimpleNamespace(
        data=None,
        processed_at=None,
        last_error=None,
        updated_at=None,
    )

    class Query:
        def __init__(self, entity):
            self.entity = entity

        def distinct(self):
            return self

        def filter(self, *args):
            return self

        def all(self):
            if self.entity is CompanySubscription.unp:
                return [(193712492,)]
            raise AssertionError(f"Unexpected all() query for {self.entity!r}")

        def first(self):
            return raw_row

    class DB:
        def __init__(self):
            self.commits = 0

        def query(self, entity):
            return Query(entity)

        def commit(self):
            self.commits += 1

        def rollback(self):
            raise AssertionError("refresh should not roll back")

    class Service:
        def __init__(self):
            self.db = DB()
            self.processed = []
            self.closed = False

        def process_raw_data(self, unp, raw_entry=None):
            self.processed.append((unp, raw_entry))

        def close(self):
            self.closed = True

    class Client:
        def __init__(self, base_url):
            self.base_url = base_url

        async def get_full_company_history(self, unp):
            return {"base_info": {"ngrn": unp}}

        async def get_events(self, unp):
            return [{"NGR04004": 77, "dfrom": "2026-08-11"}]

        async def close(self):
            return None

    service = Service()
    emitted = []
    monkeypatch.setattr(sync_tasks.settings, "EGR_API_URL", "https://egr.example")
    monkeypatch.setattr(sync_tasks, "AggregatorService", lambda: service)
    monkeypatch.setattr(sync_tasks, "EGRClient", Client)
    monkeypatch.setattr(
        sync_tasks,
        "emit_egr_source_events",
        lambda db, unp, rows: emitted.append((db, unp, rows)) or 1,
    )

    refreshed = sync_tasks.refresh_subscribed_companies.run(batch_size=10)

    assert refreshed == 1
    assert service.processed == [(193712492, raw_row)]
    assert emitted == [
        (service.db, 193712492, [{"NGR04004": 77, "dfrom": "2026-08-11"}])
    ]
    assert service.db.commits == 2
    assert service.closed is True
