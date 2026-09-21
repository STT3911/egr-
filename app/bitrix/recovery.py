"""Bounded, resumable recovery of missing requisites; never sends messages."""
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from app.bitrix.bitrix_client import BitrixClient, BitrixAPIError


class RecoveryClient(BitrixClient):
    READ_METHODS = {"app.info", "crm.company.list", "crm.company.get", "crm.requisite.list",
                    "crm.address.list", "crm.enum.addresstype"}
    WRITE_METHODS = {"crm.requisite.add", "crm.requisite.update", "crm.address.add", "crm.address.update"}

    def __init__(self, *args, apply=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply = apply

    async def call(self, method, params=None):
        if method not in self.READ_METHODS and not (self.apply and method in self.WRITE_METHODS):
            raise BitrixAPIError("REST method forbidden in requisite recovery mode")
        # Pace every REST request, including reads and address writes.
        await asyncio.sleep(0.6)
        return await super().call(method, params)

    async def verify_application(self):
        cfg = await self._load_settings()
        if not cfg.bitrix_client_id or not cfg.bitrix_client_secret:
            raise BitrixAPIError("Recovery requires portal-specific OAuth credentials")
        info = await self.call("app.info")
        code = str((info or {}).get("CODE") or "").strip()
        if not code or code != cfg.bitrix_client_id.strip():
            raise BitrixAPIError("Saved tokens belong to a different app; fix portal OAuth settings first")


def save_state(path, state):
    """Atomic checkpoint, no OAuth data or company field values."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".partial")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(state, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


async def discover(client, state, checkpoint):
    """Union of created and modified ranges, ID keyset pagination (50/page).

    The interval is a current-CRM selection, not reconstruction of a historic
    audit log: deleted companies and overwritten DATE_MODIFY are not recovered.
    """
    seen = set(state["company_ids"])
    for field in ("DATE_CREATE", "DATE_MODIFY"):
        progress = state["discovery"][field]
        while not progress["complete"]:
            rows = await client.call("crm.company.list", {
                "filter": {f">={field}": state["since"], f"<={field}": state["until"], ">ID": progress["last_id"]},
                "order": {"ID": "ASC"}, "select": ["ID"], "start": 0,
            })
            if not isinstance(rows, list):
                raise BitrixAPIError("Invalid company list; checkpoint unchanged")
            if not rows:
                progress["complete"] = True
            else:
                ids = [int(row["ID"]) for row in rows]
                if ids != sorted(set(ids)) or ids[0] <= progress["last_id"]:
                    raise BitrixAPIError("Non-advancing company pagination")
                seen.update(ids)
                state["company_ids"] = sorted(seen)
                progress["last_id"] = ids[-1]
            checkpoint(state)


async def recover(service, state, checkpoint, *, apply=False, limit=100):
    if limit < 1:
        raise ValueError("limit must be positive")
    if not all(item["complete"] for item in state["discovery"].values()):
        raise ValueError("Company discovery is incomplete")
    results = []
    start = state["next_index"] if apply else state.get("preview_index", 0)
    for index in range(start, min(len(state["company_ids"]), start + limit)):
        company_id = state["company_ids"][index]
        # Exceptions propagate: don't mark unsuccessful companies completed.
        result = await service.process_company_update(company_id, recovery_mode=True, dry_run=not apply)
        results.append(result)
        if apply:
            state["next_index"] = index + 1
        else:
            state["preview_index"] = index + 1
        checkpoint(state)
    return results
