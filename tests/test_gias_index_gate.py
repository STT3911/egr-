from contextlib import nullcontext
from unittest.mock import Mock
from types import SimpleNamespace
import copy
import json
import pytest

from app.services.gias_index_gate import IndexCooldown


def test_backoff_applies_to_new_tasks_and_survives_worker_restart():
    saved = []
    gate = IndexCooldown({}, lambda s: saved.append(copy.deepcopy(s)), clock=lambda: 1000)
    assert gate.fail('first') == 300
    gate = IndexCooldown(saved[-1], lambda s: saved.append(copy.deepcopy(s)), clock=lambda: 1100)
    assert gate.blocked('new-beat-job', 0)['status'] == 'cooldown'
    assert gate.blocked('first', 1)['status'] == 'cooldown'
    gate.clock = lambda: 1301
    assert gate.blocked('first', 1) is None
    assert gate.fail('first') == 600
    gate.clock = lambda: 2000
    assert gate.fail('first') == 1200
    assert gate.fail('first') == 1200


def test_success_cancels_obsolete_retry_and_resets_backoff():
    gate = IndexCooldown({}, Mock(), clock=lambda: 1000)
    gate.fail('old')
    gate.success()
    assert gate.blocked('old', 1) == {'status': 'superseded_retry'}
    assert gate.blocked('new', 0) is None
    assert gate.fail('new') == 300


def test_cooldown_does_not_build_service_or_contact_source(monkeypatch):
    from app.tasks import sync_tasks as tasks
    gate = IndexCooldown({'next_allowed_at': 2000}, Mock(), clock=lambda: 1000)
    monkeypatch.setattr(tasks, 'gias_index_gate', lambda: nullcontext(gate))
    service = Mock()
    monkeypatch.setattr(tasks, 'GiasContractService', service)
    assert tasks.sync_gias_contract_index.run()['status'] == 'cooldown'
    service.assert_not_called()
    monkeypatch.setattr(tasks, 'gias_index_gate', lambda: nullcontext(None))
    assert tasks.sync_gias_contract_index.run()['status'] == 'already_running'
    service.assert_not_called()


def test_database_gate_persists_cooldown_and_releases_lock_on_exception(monkeypatch):
    from app.services import gias_index_gate as module
    from unittest.mock import MagicMock
    row = Mock(value=json.dumps({"failures": 1, "next_allowed_at": 0}))
    connection = MagicMock()
    connection.execute.return_value.scalar.return_value = True
    transaction = MagicMock()
    transaction.__enter__.return_value = connection
    db = MagicMock()
    db.__enter__.return_value = db
    db.query.return_value.filter.return_value.first.return_value = row
    monkeypatch.setattr(module.engine, "begin", lambda: transaction)
    monkeypatch.setattr(module, "SessionLocal", lambda: db)
    with pytest.raises(RuntimeError):
        with module.gias_index_gate() as gate:
            assert gate.fail("owner") == 600
            raise RuntimeError("task retry")
    assert json.loads(row.value)["retry_task_id"] == "owner"
    db.commit.assert_called_once()
    assert transaction.__exit__.call_args.args[0] is RuntimeError


def test_coordination_storage_failure_never_contacts_source(monkeypatch):
    from app.tasks import sync_tasks as tasks
    monkeypatch.setattr(tasks, 'gias_index_gate', Mock(side_effect=RuntimeError("DB unavailable")))
    service = Mock()
    monkeypatch.setattr(tasks, 'GiasContractService', service)
    with pytest.raises(RuntimeError):
        tasks.sync_gias_contract_index.run()
    service.assert_not_called()


@pytest.mark.parametrize("status", ["cooldown", "superseded_retry", "already_running"])
def test_coordination_skip_is_not_success_notification(monkeypatch, status):
    from app.tasks import parser_alerts
    monkeypatch.setattr(parser_alerts.settings, "PARSER_ALERTS_NOTIFY_SUCCESS", True)
    alert = Mock()
    monkeypatch.setattr(parser_alerts, "send_telegram_alert", alert)
    parser_alerts.parser_task_finished(
        sender=SimpleNamespace(name="app.tasks.sync_tasks.sync_gias_contract_index"),
        task=None, state="SUCCESS", retval={"status": status})
    alert.assert_not_called()
