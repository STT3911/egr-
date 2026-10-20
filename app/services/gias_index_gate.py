"""Cross-task backoff for the GIAS contract index, persisted across workers."""
from contextlib import contextmanager
import json
import time

from sqlalchemy import text
from app.core.database import engine, SessionLocal
from app.database.models import SystemState

KEY = "gias_contract_index_cooldown_v1"


class IndexCooldown:
    def __init__(self, state, save, clock=time.time):
        self.state, self.save, self.clock = state, save, clock

    def blocked(self, task_id, retries):
        if retries and self.state.get("retry_task_id") != task_id:
            return {"status": "superseded_retry"}
        remaining = self.state.get("next_allowed_at", 0) - self.clock()
        if remaining > 0:
            return {"status": "cooldown", "retry_after_seconds": int(remaining) + 1}
        return None

    def fail(self, task_id):
        failures = min(4, int(self.state.get("failures", 0)) + 1)
        delay = min(1200, 300 * 2 ** (failures - 1))
        self.state = {"failures": failures, "next_allowed_at": self.clock() + delay,
                      "retry_task_id": task_id}
        self.save(self.state)
        return delay

    def success(self):
        self.state = {"failures": 0, "next_allowed_at": 0, "retry_task_id": None}
        self.save(self.state)


@contextmanager
def gias_index_gate():
    # A separate transaction holds this lock while the importer commits pages.
    # No Redis fail-open: if coordination storage fails, do not contact GIAS.
    with engine.begin() as lock:
        acquired = lock.execute(text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"),
                                {"key": KEY}).scalar()
        if not acquired:
            yield None
            return
        with SessionLocal() as db:
            row = db.query(SystemState).filter(SystemState.key == KEY).first()
            state = json.loads(row.value) if row else {}

            def save(value):
                nonlocal row
                if row is None:
                    row = SystemState(key=KEY)
                    db.add(row)
                row.value = json.dumps(value)
                db.commit()

            yield IndexCooldown(state, save)
