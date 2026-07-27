"""Resumable synchronization of public contracts from gias.by."""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import requests
from requests.adapters import HTTPAdapter
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from urllib3.util.retry import Retry

from app.core.config import settings
from app.core.logger import get_logger
from app.database.models import (
    Company,
    GiasContract,
    GiasContractPosition,
    GiasContractSyncState,
    GiasSyncRun,
)
from app.services.company_registry import (
    sync_company_from_gias,
    sync_company_from_grp,
)
from app.services.unp_probe import DualSourceProbe


logger = get_logger("gias_contracts")


@dataclass
class ContractSyncStats:
    registry_name: str
    fetched: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0
    pages: int = 0


class GiasContractService:
    """Fetch contract index/details and connect both parties to central companies."""

    def __init__(self, db: Session):
        self.db = db
        self.search_url = settings.GIAS_CONTRACT_SEARCH_URL
        self.detail_url = settings.GIAS_CONTRACT_DETAIL_URL.rstrip("/")
        self.timeout = max(1.0, float(settings.GIAS_CONTRACT_TIMEOUT_SECONDS))
        self.page_size = max(1, min(100, int(settings.GIAS_CONTRACT_PAGE_SIZE)))
        self.request_delay = max(
            0.0, float(settings.GIAS_CONTRACT_REQUEST_DELAY_SECONDS)
        )
        self.request_interval = max(
            0.0, float(settings.GIAS_CONTRACT_REQUEST_INTERVAL_SECONDS)
        )
        self.detail_concurrency = max(
            1, min(8, int(settings.GIAS_CONTRACT_DETAIL_CONCURRENCY))
        )
        self._thread_local = threading.local()
        self._worker_sessions: list[requests.Session] = []
        self._worker_sessions_lock = threading.Lock()
        self._request_start_lock = threading.Lock()
        self._next_request_start = 0.0
        self.session = self._build_http_session()

    def _build_http_session(self) -> requests.Session:
        session = requests.Session()
        retries = Retry(
            total=4,
            connect=4,
            read=4,
            status=4,
            backoff_factor=1.0,
            status_forcelist=(408, 425, 429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            respect_retry_after_header=True,
        )
        session.mount("https://", HTTPAdapter(max_retries=retries))
        session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "Origin": "https://gias.by",
                "Referer": "https://gias.by/gias/",
                "User-Agent": "EGR-Aggregator/1.0 (+public GIAS contracts sync)",
            }
        )
        return session

    def close(self) -> None:
        self.session.close()
        with self._worker_sessions_lock:
            sessions = list(self._worker_sessions)
            self._worker_sessions.clear()
        for session in sessions:
            session.close()

    def sync_index(
        self,
        *,
        full: bool = False,
        max_pages: int | None = None,
    ) -> dict[str, Any]:
        """Upsert the paginated contract index; details remain a DB-backed queue."""
        stats = ContractSyncStats(registry_name="contracts_index")
        run = self._start_run(stats.registry_name)
        state = self._get_sync_state(reset=full)
        initial_mode = not state.initial_complete
        cutoff = None
        if not initial_mode:
            latest = self.db.query(func.max(GiasContract.source_updated_at)).scalar()
            if latest:
                cutoff = latest - timedelta(
                    hours=max(
                        1,
                        int(settings.GIAS_CONTRACT_INCREMENTAL_LOOKBACK_HOURS),
                    )
                )

        page = int(state.next_page or 0) if initial_mode else 0
        try:
            while max_pages is None or stats.pages < max_pages:
                payload = self._fetch_index_page(page)
                items = payload.get("content") or []
                if not items:
                    if initial_mode:
                        state.initial_complete = True
                        state.next_page = 0
                        self.db.commit()
                    break

                contract_ids = [
                    contract_id
                    for contract_id in (
                        self._uuid_or_none(item.get("contractId"))
                        for item in items
                    )
                    if contract_id is not None
                ]
                existing_by_id = {
                    row.contract_id: row
                    for row in (
                        self.db.query(GiasContract)
                        .filter(GiasContract.contract_id.in_(contract_ids))
                        .all()
                    )
                }
                page_oldest: datetime | None = None
                for item in items:
                    source_updated = self._ms_to_dt(item.get("dtUpdate"))
                    if source_updated and (
                        page_oldest is None or source_updated < page_oldest
                    ):
                        page_oldest = source_updated
                    outcome = self._upsert_summary(
                        item,
                        existing=existing_by_id.get(
                            self._uuid_or_none(item.get("contractId"))
                        ),
                    )
                    setattr(stats, outcome, getattr(stats, outcome) + 1)

                stats.fetched += len(items)
                stats.pages += 1
                next_page = page + 1
                total_pages = payload.get("totalPages")
                if initial_mode:
                    state.total_pages = (
                        int(total_pages) if total_pages is not None else None
                    )
                    reached_end = (
                        (total_pages is not None and next_page >= int(total_pages))
                        or len(items) < self.page_size
                    )
                    state.initial_complete = reached_end
                    state.next_page = 0 if reached_end else next_page
                self.db.commit()
                logger.info(
                    "GIAS contract index: page=%s fetched=%s total=%s initial=%s",
                    page,
                    len(items),
                    stats.fetched,
                    initial_mode,
                )

                page = next_page
                if total_pages is not None and page >= int(total_pages):
                    break
                if len(items) < self.page_size:
                    break
                if cutoff and page_oldest and page_oldest < cutoff:
                    break

            run.status = (
                "partial"
                if initial_mode and not state.initial_complete
                else "success"
            )
            self._finish_run(run, stats)
            self.db.commit()
            return stats.__dict__
        except Exception as exc:
            self.db.rollback()
            self._fail_run(run, exc)
            self.db.commit()
            raise

    def fetch_pending_details(self, limit: int) -> dict[str, Any]:
        """Fetch a bounded batch of detail cards and normalize their positions."""
        stats = ContractSyncStats(registry_name="contract_details")
        run = self._start_run(stats.registry_name)
        now = datetime.utcnow()
        rows = (
            self.db.query(GiasContract)
            .filter(GiasContract.detail_status.in_(("pending", "error")))
            .filter(
                or_(
                    GiasContract.detail_next_retry_at.is_(None),
                    GiasContract.detail_next_retry_at <= now,
                )
            )
            .order_by(
                GiasContract.source_updated_at.desc().nullslast(),
                GiasContract.contract_id,
            )
            .limit(max(1, int(limit)))
            .all()
        )

        try:
            futures = self._schedule_detail_requests(rows)
            for contract in rows:
                stats.fetched += 1
                try:
                    detail = futures[contract.contract_id].result()
                    self._apply_detail(contract, detail)
                    self.db.commit()
                    stats.updated += 1
                except Exception as exc:
                    self.db.rollback()
                    failed = self.db.get(GiasContract, contract.contract_id)
                    if failed is not None:
                        failed.detail_status = "error"
                        failed.detail_attempts = int(failed.detail_attempts or 0) + 1
                        failed.detail_last_error = str(exc)[:4000]
                        delay_minutes = min(
                            24 * 60,
                            2 ** min(failed.detail_attempts, 10),
                        )
                        failed.detail_next_retry_at = datetime.utcnow() + timedelta(
                            minutes=delay_minutes
                        )
                        self.db.commit()
                    stats.failed += 1
                    logger.warning(
                        "GIAS contract detail %s failed: %s",
                        contract.contract_id,
                        exc,
                    )
            run = self.db.get(GiasSyncRun, run.id)
            run.status = "success" if stats.failed == 0 else "partial"
            self._finish_run(run, stats)
            self.db.commit()
            return stats.__dict__
        except Exception as exc:
            self.db.rollback()
            run = self.db.get(GiasSyncRun, run.id)
            self._fail_run(run, exc)
            self.db.commit()
            raise

    def resolve_contract_companies(self, limit: int) -> dict[str, int]:
        """Resolve missing party UNPs through EGR+GRP, then GIAS fallback."""
        return asyncio.run(self._resolve_contract_companies(max(1, int(limit))))

    async def _resolve_contract_companies(self, limit: int) -> dict[str, int]:
        parties = self._collect_unresolved_parties(limit)
        stats = {"checked": 0, "linked": 0, "gias_fallback": 0, "errors": 0}
        if not parties:
            return stats

        probe = DualSourceProbe()
        try:
            for unp, name, address in parties:
                stats["checked"] += 1
                company = self.db.query(Company).filter(Company.unp == unp).first()
                if company is None:
                    if sync_company_from_grp(self.db, unp):
                        self.db.commit()
                    else:
                        result = await probe.probe(
                            str(unp),
                            need_egr=True,
                            need_grp=True,
                            max_retries=1,
                            retry_delay=1.0,
                            cooldown=10.0,
                        )
                        self.db.expire_all()
                        company = (
                            self.db.query(Company)
                            .filter(Company.unp == unp)
                            .first()
                        )
                        if company is None and result.outcome == "miss":
                            company = sync_company_from_gias(
                                self.db,
                                unp,
                                name=name,
                                address=address,
                            )
                            self.db.commit()
                            stats["gias_fallback"] += 1
                        elif company is None:
                            stats["errors"] += 1
                            continue

                company = (
                    self.db.query(Company).filter(Company.unp == unp).one()
                )
                customer_count = (
                    self.db.query(GiasContract)
                    .filter(
                        GiasContract.customer_unp == unp,
                        GiasContract.customer_company_id.is_(None),
                    )
                    .update(
                        {"customer_company_id": company.id},
                        synchronize_session=False,
                    )
                )
                provider_count = (
                    self.db.query(GiasContract)
                    .filter(
                        GiasContract.provider_unp == unp,
                        GiasContract.provider_company_id.is_(None),
                    )
                    .update(
                        {"provider_company_id": company.id},
                        synchronize_session=False,
                    )
                )
                self.db.commit()
                stats["linked"] += int(customer_count or 0) + int(
                    provider_count or 0
                )
        finally:
            await probe.close()
        return stats

    def _collect_unresolved_parties(
        self, limit: int
    ) -> list[tuple[int, str | None, str | None]]:
        result: dict[int, tuple[str | None, str | None]] = {}
        scan_limit = max(limit * 4, limit)
        customers = (
            self.db.query(
                GiasContract.customer_unp,
                GiasContract.customer_name,
                GiasContract.customer_location,
            )
            .filter(
                GiasContract.customer_unp.isnot(None),
                GiasContract.customer_company_id.is_(None),
            )
            .limit(scan_limit)
            .all()
        )
        providers = (
            self.db.query(
                GiasContract.provider_unp,
                GiasContract.provider_name,
                GiasContract.provider_address,
            )
            .filter(
                GiasContract.provider_unp.isnot(None),
                GiasContract.provider_company_id.is_(None),
            )
            .limit(scan_limit)
            .all()
        )
        for unp, name, address in [*customers, *providers]:
            if unp is not None:
                result.setdefault(int(unp), (name, address))
            if len(result) >= limit:
                break
        return [(unp, *values) for unp, values in result.items()]

    def _fetch_index_page(self, page: int) -> dict[str, Any]:
        body = {
            "baseContractId": None,
            "page": page,
            "pageSize": self.page_size,
            "sortField": "dtUpdate",
            "sortOrder": "DESC",
        }
        response = self.session.post(
            self.search_url,
            json=body,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(
            payload.get("content"), list
        ):
            raise ValueError("Unsupported GIAS contract search response")
        return payload

    def _fetch_detail(self, contract_id: UUID) -> dict[str, Any]:
        return self._fetch_detail_with_session(self.session, contract_id)

    def _fetch_detail_with_session(
        self,
        session: requests.Session,
        contract_id: UUID,
    ) -> dict[str, Any]:
        response = session.get(
            f"{self.detail_url}/{contract_id}",
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Unsupported GIAS contract detail response")
        if str(payload.get("contractId")) != str(contract_id):
            raise ValueError("GIAS contract detail returned a different contractId")
        return payload

    def _worker_session(self) -> requests.Session:
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = self._build_http_session()
            self._thread_local.session = session
            with self._worker_sessions_lock:
                self._worker_sessions.append(session)
        return session

    def _fetch_detail_worker(self, contract_id: UUID) -> dict[str, Any]:
        try:
            self._wait_for_request_slot()
            return self._fetch_detail_with_session(
                self._worker_session(),
                contract_id,
            )
        finally:
            # Preserve the original per-request cooldown in addition to the
            # global request-start interval.
            if self.request_delay:
                time.sleep(self.request_delay)

    def _wait_for_request_slot(self) -> None:
        """Guarantee spacing between actual HTTP starts across all workers."""
        with self._request_start_lock:
            remaining = self._next_request_start - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            self._next_request_start = time.monotonic() + self.request_interval

    def _schedule_detail_requests(
        self,
        rows: list[GiasContract],
    ) -> dict[UUID, Future[dict[str, Any]]]:
        """Start detail requests at a fixed global pace and cap concurrency."""
        futures: dict[UUID, Future[dict[str, Any]]] = {}
        executor = ThreadPoolExecutor(
            max_workers=self.detail_concurrency,
            thread_name_prefix="gias-detail",
        )
        try:
            for contract in rows:
                futures[contract.contract_id] = executor.submit(
                    self._fetch_detail_worker,
                    contract.contract_id,
                )
        finally:
            executor.shutdown(wait=False)
        return futures

    def _upsert_summary(
        self,
        payload: dict[str, Any],
        *,
        existing: GiasContract | None,
    ) -> str:
        contract_id = self._uuid_or_none(payload.get("contractId"))
        if contract_id is None:
            raise ValueError("GIAS contract index item has no contractId")
        normalized = self._summary_values(payload)
        digest = self._hash_json(payload)
        if existing is None:
            self.db.add(
                GiasContract(
                    contract_id=contract_id,
                    sync_hash=digest,
                    raw_summary=payload,
                    **normalized,
                )
            )
            return "created"

        existing.last_seen_at = datetime.utcnow()
        if existing.sync_hash == digest:
            return "unchanged"
        for key, value in normalized.items():
            setattr(existing, key, value)
        existing.raw_summary = payload
        existing.sync_hash = digest
        existing.detail_status = "pending"
        existing.detail_last_error = None
        existing.detail_next_retry_at = None
        return "updated"

    def _apply_detail(
        self, contract: GiasContract, payload: dict[str, Any]
    ) -> None:
        values = self._summary_values(payload)
        customer = payload.get("customer") or {}
        for key, value in values.items():
            setattr(contract, key, value)
        contract.base_contract_id = self._uuid_or_none(payload.get("baseContractId"))
        contract.chain_uuid = self._uuid_or_none(payload.get("chainUuid"))
        contract.customer_gias_uuid = self._uuid_or_none(customer.get("uuid"))
        contract.customer_region = customer.get("region")
        contract.customer_city_name = self._clean_text(customer.get("cityName"))
        contract.customer_okogu_code = customer.get("okogu")
        contract.provider_unp = self._unp_to_int(payload.get("unpProvider"))
        contract.provider_name = self._clean_text(payload.get("titleProvider"))
        contract.provider_address = self._clean_text(payload.get("addressProvider"))
        contract.provider_country = self._clean_text(payload.get("countryProvider"))
        contract.provider_country_name = self._clean_text(
            payload.get("countryProviderStr")
        )
        contract.state_asfr = self._clean_text(payload.get("stateAsfr"))
        contract.contract_type = self._clean_text(payload.get("contractType"))
        contract.ets_id = self._clean_text(payload.get("etsId"))
        contract.contract_date = self._ms_to_dt(payload.get("contractDate"))
        contract.execution_term = self._ms_to_dt(payload.get("executionTerm"))
        contract.real_execution_term = self._ms_to_dt(
            payload.get("realExecutionTerm")
        )
        contract.termination_execution_term = self._ms_to_dt(
            payload.get("terminationExecutionTerm")
        )
        contract.termination_reason = self._clean_text(
            payload.get("terminationReason")
        )
        contract.has_smp = payload.get("hasSmp")
        contract.raw_detail = payload
        contract.detail_status = "fetched"
        contract.detail_attempts = 0
        contract.detail_last_error = None
        contract.detail_next_retry_at = None
        contract.detail_fetched_at = datetime.utcnow()
        contract.last_seen_at = datetime.utcnow()

        customer_company = self._find_company(contract.customer_unp)
        provider_company = self._find_company(contract.provider_unp)
        contract.customer_company_id = (
            customer_company.id if customer_company else None
        )
        contract.provider_company_id = (
            provider_company.id if provider_company else None
        )

        self.db.query(GiasContractPosition).filter(
            GiasContractPosition.contract_id == contract.contract_id
        ).delete(synchronize_session=False)
        for item in payload.get("contractPositions") or []:
            position = self._normalize_position(contract.contract_id, item)
            if position is not None:
                self.db.add(position)

    def _summary_values(self, payload: dict[str, Any]) -> dict[str, Any]:
        customer = payload.get("customer") or {}
        return {
            "customer_unp": self._unp_to_int(customer.get("unp")),
            "customer_name": self._clean_text(customer.get("name")),
            "customer_location": self._clean_text(customer.get("location")),
            "state": self._clean_text(payload.get("state")),
            "title": self._clean_text(payload.get("titleContract")),
            "price": self._decimal_or_none(payload.get("contractPrice")),
            "currency_code": self._clean_text(
                payload.get("contractPriceCurrencyCode")
            ),
            "plan_number": self._clean_text(payload.get("planNumber")),
            "contract_number": self._clean_text(payload.get("contractNum")),
            "registration_number": self._clean_text(payload.get("regNumber")),
            "source_created_at": self._ms_to_dt(payload.get("dtCreate")),
            "source_updated_at": self._ms_to_dt(payload.get("dtUpdate")),
        }

    def _normalize_position(
        self, contract_id: UUID, payload: dict[str, Any]
    ) -> GiasContractPosition | None:
        position_id = self._uuid_or_none(payload.get("id"))
        if position_id is None:
            return None
        lot = payload.get("lot") or {}
        okpb = payload.get("okpb") or {}
        unit = payload.get("unit") or {}
        return GiasContractPosition(
            id=position_id,
            contract_id=contract_id,
            public_number=self._clean_text(payload.get("publicNumber")),
            title=self._clean_text(payload.get("titlePosition")),
            lot_uuid=self._uuid_or_none(lot.get("uuid")),
            lot_number=lot.get("lotNumber"),
            lot_title=self._clean_text(lot.get("titleLot")),
            okpb_uuid=self._uuid_or_none(okpb.get("uuid")),
            okpb_code=self._clean_text(okpb.get("code")),
            okpb_name=self._clean_text(okpb.get("name")),
            volume=self._decimal_or_none(payload.get("volume")),
            unit_uuid=self._uuid_or_none(unit.get("uuid")),
            unit_code=self._clean_text(unit.get("code")),
            unit_name=self._clean_text(unit.get("name")),
            unit_symbol=self._clean_text(unit.get("symbol")),
            position_type=self._clean_text(payload.get("type")),
            unit_price=self._decimal_or_none(payload.get("unitPrice")),
            position_price=self._decimal_or_none(payload.get("positionPrice")),
            countries=payload.get("countryProducts"),
            country_names=payload.get("countryProductsStr"),
            is_smp=payload.get("isSmp"),
            source_created_at=self._ms_to_dt(payload.get("dtCreate")),
            source_updated_at=self._ms_to_dt(payload.get("dtUpdate")),
            raw_json=payload,
        )

    def _find_company(self, unp: int | None) -> Company | None:
        if unp is None:
            return None
        return self.db.query(Company).filter(Company.unp == unp).first()

    def _start_run(self, registry_name: str) -> GiasSyncRun:
        run = GiasSyncRun(registry_name=registry_name, status="running")
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def _get_sync_state(self, *, reset: bool) -> GiasContractSyncState:
        state = self.db.get(GiasContractSyncState, 1)
        if state is None:
            state = GiasContractSyncState(id=1)
            self.db.add(state)
        if reset:
            state.next_page = 0
            state.total_pages = None
            state.initial_complete = False
        self.db.commit()
        self.db.refresh(state)
        return state

    @staticmethod
    def _finish_run(run: GiasSyncRun, stats: ContractSyncStats) -> None:
        run.finished_at = datetime.utcnow()
        run.records_fetched = stats.fetched
        run.created_count = stats.created
        run.updated_count = stats.updated
        run.unchanged_count = stats.unchanged
        run.history_created_count = 0
        if stats.failed:
            run.error = f"{stats.failed} records failed"

    @staticmethod
    def _fail_run(run: GiasSyncRun, exc: Exception) -> None:
        run.status = "failed"
        run.finished_at = datetime.utcnow()
        run.error = str(exc)[:4000]

    @staticmethod
    def _hash_json(payload: dict[str, Any]) -> str:
        raw = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @staticmethod
    def _uuid_or_none(value: Any) -> UUID | None:
        if not value:
            return None
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _unp_to_int(value: Any) -> int | None:
        text = str(value or "").strip()
        if not text.isdigit():
            return None
        return int(text)

    @staticmethod
    def _ms_to_dt(value: Any) -> datetime | None:
        if value in (None, "", 0):
            return None
        try:
            return datetime.utcfromtimestamp(int(value) / 1000.0)
        except (TypeError, ValueError, OSError):
            return None

    @staticmethod
    def _decimal_or_none(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
