"""Dual-source probing for checksum-valid UNP candidates."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

import httpx

from app.core.database import SessionLocal
from app.crud.grp import GrpCRUD
from app.services.aggregator import AggregatorService
from app.services.company_registry import sync_company_from_grp
from app.services.grp_client import GRPClient


SourceStatus = Literal["skipped", "found", "not_found", "error"]


@dataclass(frozen=True)
class SourceResult:
    source: Literal["egr", "grp"]
    status: SourceStatus
    payload: dict | None = None
    http_status: int | None = None
    source_variant: str = ""
    error: str = ""


@dataclass(frozen=True)
class DualProbeResult:
    unp: str
    egr: SourceResult
    grp: SourceResult
    persist_errors: tuple[str, ...] = ()

    @property
    def outcome(self) -> Literal["hit", "miss", "error"]:
        if (
            self.persist_errors
            or self.egr.status == "error"
            or self.grp.status == "error"
        ):
            return "error"
        if self.egr.status in {"found", "skipped"} or self.grp.status in {
            "found",
            "skipped",
        }:
            return "hit"
        if self.egr.status == "not_found" and self.grp.status == "not_found":
            return "miss"
        return "error"

    @property
    def new_found(self) -> int:
        return int(self.egr.status == "found" or self.grp.status == "found")

    @property
    def error(self) -> str:
        values = [
            self.egr.error if self.egr.status == "error" else "",
            self.grp.error if self.grp.status == "error" else "",
            *self.persist_errors,
        ]
        return " | ".join(value for value in values if value)


def _first_dict(payload: object) -> dict | None:
    if isinstance(payload, dict):
        return payload or None
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    return None


def _dict_list(payload: object) -> list[dict]:
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


async def _egr_request(
    client_object: object,
    endpoint: str,
    params: dict | None = None,
) -> object | None:
    http_client = await client_object._get_client()
    response = await http_client.get(
        f"{client_object.base_url}/{endpoint}",
        params=params,
    )
    if response.status_code in {204, 400, 404}:
        return None
    response.raise_for_status()
    try:
        return response.json()
    except ValueError as exc:
        raise ValueError(f"EGR returned non-JSON for {endpoint}: {exc}") from exc


async def _fetch_egr_once(
    aggregator: AggregatorService,
    unp: str,
) -> tuple[dict | None, str]:
    legacy_payload = await _egr_request(
        aggregator.egr_client,
        f"getBaseInfoByRegNum/{int(unp)}",
    )
    base_info = _first_dict(legacy_payload)
    if base_info:
        is_juridical = base_info.get("nsi00211", {}).get("nkvob") == 1
        name_endpoint = (
            "getAllJurNamesByRegNum"
            if is_juridical
            else "getAllIPFIOByRegNum"
        )
        addresses_raw, ved_raw, names_raw = await asyncio.gather(
            _egr_request(
                aggregator.egr_client,
                f"getAllAddressByRegNum/{int(unp)}",
            ),
            _egr_request(
                aggregator.egr_client,
                f"getAllVEDByRegNum/{int(unp)}",
            ),
            _egr_request(
                aggregator.egr_client,
                f"{name_endpoint}/{int(unp)}",
            ),
        )
        return {
            "base_info": base_info,
            "addresses": _dict_list(addresses_raw),
            "ved": _dict_list(ved_raw),
            "names": _dict_list(names_raw),
        }, "legacy"

    if aggregator.mobile_client is not None:
        try:
            mobile_payload = await _egr_request(
                aggregator.mobile_client,
                "extracts/commonInfo",
                params={"pan": unp},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code >= 500:
                return None, ""
            raise
        common_info = _first_dict(mobile_payload)
        if common_info:
            return {
                "common_info": common_info,
                "place_location": None,
            }, "mobile"

    return None, ""


async def fetch_egr(
    aggregator: AggregatorService,
    unp: str,
    *,
    max_retries: int,
    retry_delay: float,
    cooldown: float,
) -> SourceResult:
    attempt = 0
    while True:
        try:
            payload, source_variant = await _fetch_egr_once(aggregator, unp)
            if payload:
                return SourceResult(
                    source="egr",
                    status="found",
                    payload=payload,
                    http_status=200,
                    source_variant=source_variant,
                )
            return SourceResult(
                source="egr",
                status="not_found",
                http_status=404,
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            attempt += 1
            retryable = status == 429 or status is None or status >= 500
            if not retryable or attempt > max_retries:
                return SourceResult(
                    source="egr",
                    status="error",
                    http_status=status,
                    error=str(exc),
                )
            await asyncio.sleep(
                cooldown if status == 429 else retry_delay * attempt
            )
        except (httpx.HTTPError, ValueError) as exc:
            attempt += 1
            if attempt > max_retries:
                return SourceResult(
                    source="egr",
                    status="error",
                    error=str(exc),
                )
            await asyncio.sleep(retry_delay * attempt)


async def fetch_grp(
    client: GRPClient,
    unp: str,
    *,
    max_retries: int,
    retry_delay: float,
    cooldown: float,
) -> SourceResult:
    attempt = 0
    while True:
        try:
            payload = await client.get_taxpayer(int(unp))
            if not payload:
                return SourceResult(
                    source="grp",
                    status="not_found",
                    http_status=404,
                )
            returned_unp = payload.get("VUNP") or payload.get("vunp")
            if returned_unp and str(returned_unp) != unp:
                return SourceResult(
                    source="grp",
                    status="error",
                    http_status=200,
                    error=f"GRP returned UNP {returned_unp}",
                )
            return SourceResult(
                source="grp",
                status="found",
                payload=payload,
                http_status=200,
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status is not None and 400 <= status < 500 and status != 429:
                return SourceResult(
                    source="grp",
                    status="not_found",
                    http_status=status,
                )
            attempt += 1
            if attempt > max_retries:
                return SourceResult(
                    source="grp",
                    status="error",
                    http_status=status,
                    error=str(exc),
                )
            await asyncio.sleep(
                cooldown if status == 429 else retry_delay * attempt
            )
        except (httpx.HTTPError, ValueError) as exc:
            attempt += 1
            if attempt > max_retries:
                return SourceResult(
                    source="grp",
                    status="error",
                    error=str(exc),
                )
            await asyncio.sleep(retry_delay * attempt)


def _persist_egr(
    aggregator: AggregatorService,
    unp: str,
    result: SourceResult,
) -> str:
    if result.status != "found" or not result.payload:
        return ""
    try:
        raw_entry = aggregator.save_raw_payload(int(unp), result.payload)
        aggregator.process_raw_data(int(unp), raw_entry=raw_entry)
        return ""
    except Exception as exc:
        return f"EGR persist: {exc}"


def _persist_grp(unp: str, result: SourceResult) -> str:
    if result.status in {"skipped", "error"}:
        return ""
    db = SessionLocal()
    try:
        crud = GrpCRUD(db)
        numeric_unp = int(unp)
        if result.status == "found" and result.payload:
            parsed = crud.upsert_from_api(
                unp=numeric_unp,
                payload=result.payload,
                http_status=200,
            )
            if parsed is None or not sync_company_from_grp(db, numeric_unp):
                raise RuntimeError(
                    "GRP payload could not be materialized in egr_companies"
                )
        elif result.status == "not_found":
            crud.save_raw_data(
                unp=numeric_unp,
                raw_json={},
                http_status=result.http_status,
            )
        db.commit()
        return ""
    except Exception as exc:
        db.rollback()
        return f"GRP persist: {exc}"
    finally:
        db.close()


class DualSourceProbe:
    def __init__(self) -> None:
        self.aggregator = AggregatorService()
        self.grp_client = GRPClient()

    async def probe(
        self,
        unp: str,
        *,
        need_egr: bool,
        need_grp: bool,
        max_retries: int,
        retry_delay: float,
        cooldown: float,
    ) -> DualProbeResult:
        egr_task = (
            fetch_egr(
                self.aggregator,
                unp,
                max_retries=max_retries,
                retry_delay=retry_delay,
                cooldown=cooldown,
            )
            if need_egr
            else None
        )
        grp_task = (
            fetch_grp(
                self.grp_client,
                unp,
                max_retries=max_retries,
                retry_delay=retry_delay,
                cooldown=cooldown,
            )
            if need_grp
            else None
        )
        active_tasks = [
            task for task in (egr_task, grp_task) if task is not None
        ]
        fetched = await asyncio.gather(*active_tasks)
        fetched_iter = iter(fetched)
        egr_result = (
            next(fetched_iter)
            if egr_task is not None
            else SourceResult(source="egr", status="skipped")
        )
        grp_result = (
            next(fetched_iter)
            if grp_task is not None
            else SourceResult(source="grp", status="skipped")
        )

        persist_errors = tuple(
            error
            for error in (
                _persist_egr(self.aggregator, unp, egr_result),
                _persist_grp(unp, grp_result),
            )
            if error
        )
        return DualProbeResult(
            unp=unp,
            egr=egr_result,
            grp=grp_result,
            persist_errors=persist_errors,
        )

    async def close(self) -> None:
        await self.grp_client.close()
        await self.aggregator.egr_client.close()
        if self.aggregator.mobile_client is not None:
            await self.aggregator.mobile_client.close()
        self.aggregator.close()
