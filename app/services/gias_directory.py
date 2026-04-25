"""Synchronization service for GIAS directory registries."""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import requests
from requests import Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import get_logger
from app.database.models import Company
from app.database.models import (
    GiasAccreditedCustomer,
    GiasAccreditedCustomerHistory,
    GiasSyncRun,
    LockedSupplier,
    LockedSupplierAuthor,
    LockedSupplierHistory,
    LockedSupplierReason,
)
from app.services.aggregator import AggregatorService

logger = get_logger("gias_directory")


@dataclass
class SyncStats:
    registry_name: str
    fetched: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    history_created: int = 0


class GiasDirectoryService:
    """Service for fetching and persisting GIAS registry data."""

    def __init__(self, db: Session):
        self.db = db
        self.base_url = settings.GIAS_DIRECTORY_API_URL.rstrip("/")
        self.page_size = max(1, settings.GIAS_DIRECTORY_PAGE_SIZE)
        self.timeout = settings.GIAS_DIRECTORY_TIMEOUT_SECONDS
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self._company_cache: dict[int, Company | None] = {}

    def close(self) -> None:
        self.session.close()

    def sync_all(self) -> dict[str, Any]:
        accredited = self.sync_accredited_customers()
        locked = self.sync_locked_suppliers()
        return {
            "accredited_customers": accredited.__dict__,
            "locked_suppliers": locked.__dict__,
        }

    def sync_accredited_customers(self) -> SyncStats:
        stats = SyncStats(registry_name="accredited_customers")
        run = self._start_run(stats.registry_name)
        try:
            records = self._fetch_all_pages("accredited_customers/page")
            stats.fetched = len(records)

            for payload in records:
                normalized = self._normalize_accredited_customer(payload)
                if not normalized["unp"]:
                    logger.warning("Skip accredited customer without UNP: %s", payload)
                    continue

                history_payload = normalized.pop("history_payload")
                raw_json = normalized["raw_json"]
                sync_hash = normalized["sync_hash"]
                unp = normalized["unp"]
                company = self._resolve_company(unp)
                if company is None:
                    logger.warning("Skip accredited customer %s: company not found in EGR", unp)
                    continue
                normalized["company_id"] = company.id

                existing = (
                    self.db.query(GiasAccreditedCustomer)
                    .filter(GiasAccreditedCustomer.unp == unp)
                    .one_or_none()
                )

                if existing is None:
                    customer = GiasAccreditedCustomer(**normalized)
                    self.db.add(customer)
                    self.db.flush()
                    self._append_accredited_history(customer, "create", history_payload, raw_json)
                    stats.created += 1
                    stats.history_created += 1
                    continue

                existing.last_seen_at = datetime.utcnow()
                if existing.sync_hash == sync_hash:
                    stats.unchanged += 1
                    continue

                changed_fields = self._diff_dicts(
                    self._accredited_snapshot(existing),
                    history_payload,
                )
                normalized.pop("first_seen_at", None)
                for key, value in normalized.items():
                    setattr(existing, key, value)
                self._append_accredited_history(existing, "update", history_payload, raw_json, changed_fields)
                stats.updated += 1
                stats.history_created += 1

            run.status = "success"
            self._finish_run(run, stats)
            self.db.commit()
            return stats
        except Exception as exc:
            self.db.rollback()
            self._fail_run(run, exc)
            self.db.commit()
            raise

    def sync_locked_suppliers(self) -> SyncStats:
        stats = SyncStats(registry_name="locked_suppliers")
        run = self._start_run(stats.registry_name)
        try:
            records = self._fetch_all_pages("locked_suppliers/page")
            stats.fetched = len(records)

            for payload in records:
                normalized = self._normalize_locked_supplier(payload)
                if normalized["uuid"] is None or normalized["chain_uuid"] is None:
                    logger.warning("Skip locked supplier without uuid/chainUuid: %s", payload)
                    continue

                author_id = self._upsert_author(payload.get("author") or {})
                base_incl_id = self._upsert_reason("INCLUDE", payload.get("baseincl"))
                base_excl_id = self._upsert_reason("EXCLUDE", payload.get("baseexcl"))
                history_payload = normalized.pop("history_payload")
                raw_json = normalized["raw_json"]
                sync_hash = normalized["sync_hash"]
                company = self._resolve_company(normalized["provider_unp"])
                if company is None:
                    logger.warning(
                        "Skip locked supplier %s: company not found in EGR",
                        normalized["provider_unp"],
                    )
                    continue

                existing = (
                    self.db.query(LockedSupplier)
                    .filter(LockedSupplier.uuid == normalized["uuid"])
                    .one_or_none()
                )

                normalized["author_id"] = author_id
                normalized["base_incl_id"] = base_incl_id
                normalized["base_excl_id"] = base_excl_id
                normalized["company_id"] = company.id

                if existing is None:
                    supplier = LockedSupplier(**normalized)
                    self.db.add(supplier)
                    self.db.flush()
                    self._append_locked_history(supplier, "create", history_payload, raw_json)
                    stats.created += 1
                    stats.history_created += 1
                    continue

                existing.last_seen_at = datetime.utcnow()
                if existing.sync_hash == sync_hash:
                    stats.unchanged += 1
                    continue

                changed_fields = self._diff_dicts(
                    self._locked_supplier_snapshot(existing),
                    history_payload,
                )
                normalized.pop("first_seen_at", None)
                for key, value in normalized.items():
                    setattr(existing, key, value)
                self._append_locked_history(existing, "update", history_payload, raw_json, changed_fields)
                stats.updated += 1
                stats.history_created += 1

            run.status = "success"
            self._finish_run(run, stats)
            self.db.commit()
            return stats
        except Exception as exc:
            self.db.rollback()
            self._fail_run(run, exc)
            self.db.commit()
            raise

    def _fetch_all_pages(self, path: str) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []
        page = 0

        while True:
            response = self._request_page(path, page)
            items, total_pages = self._extract_page(response)
            if not items:
                break

            all_items.extend(items)
            page += 1

            if total_pages is not None and page >= total_pages:
                break
            if len(items) < self.page_size:
                break

        return all_items

    def _request_page(self, path: str, page: int) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        params = {
            "q": "{}",
            "page": page,
            "size": self.page_size,
        }
        response: Response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _extract_page(payload: Any) -> tuple[list[dict[str, Any]], int | None]:
        if isinstance(payload, list):
            return payload, None
        if isinstance(payload, dict):
            if isinstance(payload.get("content"), list):
                return payload["content"], payload.get("totalPages")
            for key in ("data", "items", "results"):
                if isinstance(payload.get(key), list):
                    return payload[key], payload.get("totalPages")
        raise ValueError(f"Unsupported GIAS response payload: {type(payload)!r}")

    def _start_run(self, registry_name: str) -> GiasSyncRun:
        run = GiasSyncRun(registry_name=registry_name, status="running")
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    @staticmethod
    def _finish_run(run: GiasSyncRun, stats: SyncStats) -> None:
        run.finished_at = datetime.utcnow()
        run.records_fetched = stats.fetched
        run.created_count = stats.created
        run.updated_count = stats.updated
        run.unchanged_count = stats.unchanged
        run.history_created_count = stats.history_created

    @staticmethod
    def _fail_run(run: GiasSyncRun, exc: Exception) -> None:
        run.status = "failed"
        run.finished_at = datetime.utcnow()
        run.error = str(exc)[:4000]

    def _append_accredited_history(
        self,
        customer: GiasAccreditedCustomer,
        change_type: str,
        snapshot: dict[str, Any],
        raw_json: dict[str, Any],
        changed_fields: dict[str, Any] | None = None,
    ) -> None:
        self.db.add(
            GiasAccreditedCustomerHistory(
                company_id=customer.company_id,
                customer_id=customer.id,
                unp=customer.unp,
                change_type=change_type,
                changed_fields=changed_fields,
                raw_json=raw_json,
            )
        )

    def _append_locked_history(
        self,
        supplier: LockedSupplier,
        change_type: str,
        snapshot: dict[str, Any],
        raw_json: dict[str, Any],
        changed_fields: dict[str, Any] | None = None,
    ) -> None:
        self.db.add(
            LockedSupplierHistory(
                company_id=supplier.company_id,
                supplier_id=supplier.id,
                provider_unp=snapshot.get("provider_unp"),
                supplier_name=snapshot.get("name") or "",
                chain_uuid=UUID(str(snapshot["chain_uuid"])),
                change_type=change_type,
                changed_fields=changed_fields,
                state=snapshot.get("state") or "",
                location=snapshot.get("location"),
                reg_number=snapshot.get("reg_number"),
                add_date=self._parse_datetime(snapshot.get("add_date")),
                del_date=self._parse_datetime(snapshot.get("del_date")),
                base_incl_text=snapshot.get("base_incl_text"),
                base_excl_text=snapshot.get("base_excl_text"),
                raw_json=raw_json,
            )
        )

    def _upsert_author(self, author: dict[str, Any]) -> int | None:
        author_uuid = author.get("uuid")
        if not author_uuid:
            return None

        existing = (
            self.db.query(LockedSupplierAuthor)
            .filter(LockedSupplierAuthor.uuid == UUID(str(author_uuid)))
            .one_or_none()
        )
        if existing is None:
            existing = LockedSupplierAuthor(
                uuid=UUID(str(author_uuid)),
                initials=author.get("initials") or "",
                summary=author.get("summary"),
            )
            self.db.add(existing)
            self.db.flush()
            return existing.id

        existing.initials = author.get("initials") or existing.initials
        existing.summary = author.get("summary")
        self.db.flush()
        return existing.id

    def _upsert_reason(self, kind: str, text: Any) -> int | None:
        normalized = self._clean_text(text)
        if not normalized:
            return None

        existing = (
            self.db.query(LockedSupplierReason)
            .filter(
                LockedSupplierReason.kind == kind,
                LockedSupplierReason.text == normalized,
            )
            .one_or_none()
        )
        if existing is None:
            existing = LockedSupplierReason(kind=kind, text=normalized)
            self.db.add(existing)
            self.db.flush()
            return existing.id

        return existing.id

    def _resolve_company(self, unp_value: Any) -> Company | None:
        unp = self._unp_to_int(unp_value)
        if unp is None:
            return None

        if unp in self._company_cache:
            return self._company_cache[unp]

        company = self.db.query(Company).filter(Company.unp == unp).one_or_none()
        if company is not None:
            self._company_cache[unp] = company
            return company

        logger.info("Company %s not found in EGR DB, trying to fetch it before linking GIAS data", unp)
        aggregator = AggregatorService()
        try:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                fetched = loop.run_until_complete(aggregator.fetch_and_save_raw(unp))
            finally:
                loop.close()
                asyncio.set_event_loop(None)

            if fetched:
                aggregator.process_raw_data(unp)
        except Exception as exc:
            logger.warning("Failed to fetch company %s from EGR during GIAS sync: %s", unp, exc)
        finally:
            aggregator.close()

        self.db.expire_all()
        company = self.db.query(Company).filter(Company.unp == unp).one_or_none()
        self._company_cache[unp] = company
        return company

    def _normalize_accredited_customer(self, payload: dict[str, Any]) -> dict[str, Any]:
        placements = payload.get("placements") or {}
        okogu = payload.get("okogu") or {}

        normalized = {
            "unp": self._clean_text(payload.get("unp")),
            "name": self._clean_text(payload.get("name")) or "",
            "uid_customer": self._clean_text(payload.get("uidCustomer")),
            "customer_id": self._clean_text(payload.get("customerId")),
            "summary": self._clean_text(payload.get("summary")),
            "state": self._clean_text(payload.get("state")),
            "dt_update": self._ms_to_dt(payload.get("dtUpdate")),
            "dt_from": self._ms_to_dt(payload.get("dtFrom")),
            "dt_to": self._ms_to_dt(payload.get("dtTo")),
            "is_customer": payload.get("isCustomer"),
            "is_organizator": payload.get("isOrganizator"),
            "phone": self._clean_text(payload.get("phone")),
            "email": self._clean_text(payload.get("email")),
            "web_site": self._clean_text(payload.get("webSite")),
            "region": payload.get("region"),
            "city_name": self._clean_text(payload.get("cityName")),
            "placements_address": self._clean_text(payload.get("placementsAddress")),
            "placements_country": self._clean_text(placements.get("country")),
            "placements_post_index": self._clean_text(placements.get("postIndex")),
            "placements_city": self._clean_text(placements.get("city")),
            "placements_address_detail": self._clean_text(placements.get("address")),
            "okogu_name": self._clean_text(okogu.get("name")),
            "okogu_code": okogu.get("code"),
            "raw_json": payload,
            "sync_hash": self._hash_json(payload),
            "last_seen_at": datetime.utcnow(),
        }
        normalized["history_payload"] = self._accredited_history_payload(normalized)
        normalized["first_seen_at"] = datetime.utcnow()
        return normalized

    def _normalize_locked_supplier(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            "uuid": self._uuid_or_none(payload.get("uuid")),
            "chain_uuid": self._uuid_or_none(payload.get("chainUuid")),
            "state": self._clean_text(payload.get("state")) or "",
            "name": self._clean_text(payload.get("name")) or "",
            "provider_unp": self._clean_text(payload.get("providerunp")),
            "location": self._clean_text(payload.get("location")),
            "reg_number": self._clean_text(payload.get("regnumber")),
            "add_date": self._ms_to_dt(payload.get("adddate")),
            "del_date": self._ms_to_dt(payload.get("deldate")),
            "raw_json": payload,
            "sync_hash": self._hash_json(payload),
            "last_seen_at": datetime.utcnow(),
            "first_seen_at": datetime.utcnow(),
        }
        normalized["history_payload"] = {
            "chain_uuid": str(normalized["chain_uuid"]) if normalized["chain_uuid"] else None,
            "state": normalized["state"],
            "name": normalized["name"],
            "provider_unp": normalized["provider_unp"],
            "location": normalized["location"],
            "reg_number": normalized["reg_number"],
            "add_date": normalized["add_date"].isoformat() if normalized["add_date"] else None,
            "del_date": normalized["del_date"].isoformat() if normalized["del_date"] else None,
            "base_incl_text": self._clean_text(payload.get("baseincl")),
            "base_excl_text": self._clean_text(payload.get("baseexcl")),
            "author_initials": self._clean_text((payload.get("author") or {}).get("initials")),
            "author_summary": self._clean_text((payload.get("author") or {}).get("summary")),
        }
        return normalized

    @staticmethod
    def _accredited_history_payload(data: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": data.get("name"),
            "uid_customer": data.get("uid_customer"),
            "customer_id": data.get("customer_id"),
            "summary": data.get("summary"),
            "state": data.get("state"),
            "dt_update": data["dt_update"].isoformat() if data.get("dt_update") else None,
            "dt_from": data["dt_from"].isoformat() if data.get("dt_from") else None,
            "dt_to": data["dt_to"].isoformat() if data.get("dt_to") else None,
            "is_customer": data.get("is_customer"),
            "is_organizator": data.get("is_organizator"),
            "phone": data.get("phone"),
            "email": data.get("email"),
            "web_site": data.get("web_site"),
            "region": data.get("region"),
            "city_name": data.get("city_name"),
            "placements_address": data.get("placements_address"),
            "placements_country": data.get("placements_country"),
            "placements_post_index": data.get("placements_post_index"),
            "placements_city": data.get("placements_city"),
            "placements_address_detail": data.get("placements_address_detail"),
            "okogu_name": data.get("okogu_name"),
            "okogu_code": data.get("okogu_code"),
        }

    @staticmethod
    def _accredited_snapshot(customer: GiasAccreditedCustomer) -> dict[str, Any]:
        return {
            "name": customer.name,
            "uid_customer": customer.uid_customer,
            "customer_id": customer.customer_id,
            "summary": customer.summary,
            "state": customer.state,
            "dt_update": customer.dt_update.isoformat() if customer.dt_update else None,
            "dt_from": customer.dt_from.isoformat() if customer.dt_from else None,
            "dt_to": customer.dt_to.isoformat() if customer.dt_to else None,
            "is_customer": customer.is_customer,
            "is_organizator": customer.is_organizator,
            "phone": customer.phone,
            "email": customer.email,
            "web_site": customer.web_site,
            "region": customer.region,
            "city_name": customer.city_name,
            "placements_address": customer.placements_address,
            "placements_country": customer.placements_country,
            "placements_post_index": customer.placements_post_index,
            "placements_city": customer.placements_city,
            "placements_address_detail": customer.placements_address_detail,
            "okogu_name": customer.okogu_name,
            "okogu_code": customer.okogu_code,
        }

    @staticmethod
    def _locked_supplier_snapshot(supplier: LockedSupplier) -> dict[str, Any]:
        author = supplier.author
        return {
            "chain_uuid": str(supplier.chain_uuid),
            "state": supplier.state,
            "name": supplier.name,
            "provider_unp": supplier.provider_unp,
            "location": supplier.location,
            "reg_number": supplier.reg_number,
            "add_date": supplier.add_date.isoformat() if supplier.add_date else None,
            "del_date": supplier.del_date.isoformat() if supplier.del_date else None,
            "base_incl_text": supplier.base_incl.text if supplier.base_incl else None,
            "base_excl_text": supplier.base_excl.text if supplier.base_excl else None,
            "author_initials": author.initials if author else None,
            "author_summary": author.summary if author else None,
        }

    @staticmethod
    def _diff_dicts(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
        changed: dict[str, Any] = {}
        for key in sorted(set(old) | set(new)):
            if old.get(key) != new.get(key):
                changed[key] = {"old": old.get(key), "new": new.get(key)}
        return changed

    @staticmethod
    def _hash_json(payload: dict[str, Any]) -> str:
        dumped = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(dumped.encode("utf-8")).hexdigest()

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return str(value)

    @staticmethod
    def _uuid_or_none(value: Any) -> UUID | None:
        if not value:
            return None
        return UUID(str(value))

    @staticmethod
    def _ms_to_dt(value: Any) -> datetime | None:
        if value in (None, "", 0):
            return None
        try:
            if isinstance(value, str):
                value = int(value)
            return datetime.utcfromtimestamp(int(value) / 1000.0)
        except Exception:
            return None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))

    @staticmethod
    def _unp_to_int(value: Any) -> int | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text.isdigit():
            return None
        try:
            return int(text)
        except Exception:
            return None
