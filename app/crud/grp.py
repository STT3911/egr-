"""CRUD operations for GRP taxpayer data."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional, Tuple, List

from dateutil.parser import parse as dt_parse
from sqlalchemy.orm import Session

from app.database.models import GrpTaxpayerData


def _parse_date(value: Any) -> Optional[date]:
    """Parse date from common GRP formats.

    GRP responses often use 'dd.mm.yyyy' or ISO strings.
    """
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        # dateutil handles both 'YYYY-MM-DD' and 'DD.MM.YYYY'
        return dt_parse(str(value), dayfirst=True).date()
    except Exception:
        return None


class GrpCRUD:
    def __init__(self, db: Session):
        self.db = db

    def get_by_unp(self, unp: int) -> Optional[GrpTaxpayerData]:
        return self.db.query(GrpTaxpayerData).filter(GrpTaxpayerData.unp == unp).first()

    def upsert_from_api(
        self,
        unp: int,
        payload: Optional[Dict[str, Any]],
        http_status: Optional[int] = None,
        error: Optional[str] = None,
    ) -> GrpTaxpayerData:
        """Insert/update GRP record.

        `payload` is expected to be a dict with GRP fields (VNAIMP, ...).
        We keep the whole payload in `raw` and also map the most useful fields.
        """
        record = self.get_by_unp(unp)
        if not record:
            record = GrpTaxpayerData(unp=unp)
            self.db.add(record)

        record.http_status = http_status
        record.last_error = error
        record.raw = payload

        if payload and isinstance(payload, dict):
            # Support different casings just in case
            def g(*keys: str) -> Optional[Any]:
                for k in keys:
                    if k in payload:
                        return payload.get(k)
                    lk = k.lower()
                    if lk in payload:
                        return payload.get(lk)
                return None

            record.full_name = g("VNAIMP", "vnaimp")
            record.short_name = g("VNAIMK", "vnaimk")
            record.registration_date = _parse_date(g("DREG", "dreg"))
            record.inspectorate_code = g("NMNS", "nmns")
            record.inspectorate_name = g("VMNS", "vmns")
            record.status_code = g("CKODSOST", "ckodsost")
            record.status_date = _parse_date(g("DLIKV", "dlikv"))
            record.address = g("VPADRES", "vpadres")

        self.db.flush()
        return record

    def list_recent(self, limit: int = 100, offset: int = 0) -> List[GrpTaxpayerData]:
        return (
            self.db.query(GrpTaxpayerData)
            .order_by(GrpTaxpayerData.updated_at.desc().nullslast())
            .offset(offset)
            .limit(limit)
            .all()
        )
