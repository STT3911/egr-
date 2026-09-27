import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.egr_state_reconcile import find_state_targets, SQL_BATCH_SIZE


def test_full_registry_is_split_even_when_no_targets():
    db = Mock()
    db.execute.return_value.fetchall.return_value = []
    unps = range(100000001, 100002518)
    assert find_state_targets(db, unps, 2, limit=20, seen=set()) == []
    batches = [c.args[1]['unps'] for c in db.execute.call_args_list]
    assert list(map(len, batches)) == [1000, 1000, 517]
    assert sum(batches, []) == list(unps)
    assert all(c.args[1]['state'] == 2 for c in db.execute.call_args_list)


def test_budget_stops_queries_and_deduplicates_across_states():
    db = Mock()
    db.execute.return_value.fetchall.return_value = [(1,), (1,), (2,), (3,), (4,)]
    seen = {1}
    assert find_state_targets(db, range(5000), 2, limit=2, seen=seen) == [2, 3]
    assert seen == {1, 2, 3}
    assert db.execute.call_count == 1
    assert len(db.execute.call_args.args[1]['unps']) == SQL_BATCH_SIZE


def test_empty_input_and_db_failure():
    db = Mock()
    assert find_state_targets(db, [], 2, limit=10, seen=set()) == []
    db.execute.assert_not_called()
    db.execute.side_effect = RuntimeError('DB unavailable')
    with pytest.raises(RuntimeError):
        find_state_targets(db, [1], 2, limit=10, seen=set())


def test_task_interleaves_fetch_and_bounded_db_scan_and_closes(monkeypatch):
    from app.tasks import sync_tasks as tasks
    import app.services.egr_state_reconcile as reconcile
    order = []
    async def fetch(state):
        order.append(('fetch', state))
        return [state]
    def scan(db, unps, state, **kwargs):
        order.append(('scan', state))
        return unps
    client = Mock(get_reg_nums_by_state=AsyncMock(side_effect=fetch), close=AsyncMock())
    service = Mock()
    enqueue = Mock()
    monkeypatch.setattr(tasks, 'EGRClient', lambda url: client)
    monkeypatch.setattr(tasks, 'AggregatorService', lambda: service)
    monkeypatch.setattr(tasks.egr_fetch_raw_one, 'delay', enqueue)
    monkeypatch.setattr(tasks.asyncio, 'sleep', AsyncMock())
    monkeypatch.setattr(reconcile, 'find_state_targets', scan)
    result = tasks.egr_reconcile_states.run(limit=2)
    assert order == [('fetch', 1), ('scan', 1), ('fetch', 2), ('scan', 2)]
    assert result == {'delta': 2, 'enqueued': 2, 'limit_reached': True}
    assert [c.args[0] for c in enqueue.call_args_list] == [1, 2]
    client.close.assert_awaited_once()
    service.close.assert_called_once()
