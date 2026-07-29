"""CRUD operations for GRP taxpayer data."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple, List

from dateutil.parser import parse as dt_parse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database.models import GrpTaxpayerData, GrpRawData
from app.utils.address_formatter import format_grp_address


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

    # ==================== RAW DATA (Этап 1: Сохранение сырых данных) ====================
    
    def save_raw_data(
        self,
        unp: int,
        raw_json: Optional[Dict[str, Any]],
        http_status: Optional[int] = None,
        error: Optional[str] = None,
    ) -> GrpRawData:
        """Сохранить сырые данные из API ГРП в таблицу grp_raw_data."""
        record = self.db.query(GrpRawData).filter(GrpRawData.unp == unp).first()
        
        if not record:
            self.db.execute(
                pg_insert(GrpRawData)
                .values(
                    unp=unp,
                    raw_json=raw_json or {},
                    http_status=http_status,
                    last_error=error,
                    updated_at=datetime.now(),
                    parsed=False,
                )
                .on_conflict_do_nothing(index_elements=[GrpRawData.unp])
            )
            record = (
                self.db.query(GrpRawData)
                .filter(GrpRawData.unp == unp)
                .one()
            )

        has_payload = isinstance(raw_json, dict) and bool(raw_json)
        updated_at = datetime.now()

        if has_payload and not error:
            record.raw_json = raw_json
            record.http_status = http_status
            record.last_error = None
            record.updated_at = updated_at
            # Only successful fetches invalidate the parsed snapshot.
            record.parsed = False
            record.parsed_at = None
        else:
            # Do not destroy the last good snapshot on transient fetch failures.
            if record.raw_json is None:
                record.raw_json = raw_json or {}
            record.http_status = http_status
            record.last_error = error
            record.updated_at = updated_at
            if record.parsed is None:
                record.parsed = False
            if record.parsed_at is None and not record.parsed:
                record.parsed_at = None
        
        self.db.flush()
        return record
    
    def get_raw_by_unp(self, unp: int) -> Optional[GrpRawData]:
        """Получить сырые данные по УНП."""
        return self.db.query(GrpRawData).filter(GrpRawData.unp == unp).first()
    
    def get_unparsed_raw_data(self, limit: int = 100) -> List[GrpRawData]:
        """Получить неспарсенные непустые сырые данные."""
        rows = (
            self.db.query(GrpRawData)
            .filter(GrpRawData.parsed == False)
            .filter(GrpRawData.raw_json != None)
            .filter((GrpRawData.last_error == None) | (GrpRawData.last_error == ""))
            .order_by(GrpRawData.updated_at.desc())
            .limit(limit)
            .all()
        )
        return [row for row in rows if row.raw_json]

    def upsert_from_api(
        self,
        unp: int,
        payload: Optional[Dict[str, Any]] = None,
        http_status: Optional[int] = None,
        error: Optional[str] = None,
    ) -> Optional[GrpTaxpayerData]:
        """Сохранить ответ API ГРП в raw и при наличии данных — распарсить в grp_taxpayer_data.
        Вызывается из API и скриптов после запроса к ГРП.
        """
        self.save_raw_data(unp=unp, raw_json=payload, http_status=http_status, error=error)
        if payload and not error:
            return self.parse_from_raw(unp)
        return self.get_by_unp(unp)

    # ==================== PARSED DATA (Этап 2: Парсинг в структурированную таблицу) ====================
    
    def parse_from_raw(self, unp: int) -> Optional[GrpTaxpayerData]:
        """Распарсить данные из grp_raw_data в grp_taxpayer_data."""
        raw_record = self.get_raw_by_unp(unp)
        
        if not raw_record or not raw_record.raw_json:
            return None
        
        payload = raw_record.raw_json
        
        # Парсинг полей
        def g(*keys: str) -> Optional[Any]:
            """Get value from payload with case-insensitive key matching."""
            for k in keys:
                if k in payload:
                    return payload.get(k)
                lk = k.lower()
                if lk in payload:
                    return payload.get(lk)
            return None
        
        values = {
            "unp": unp,
            "full_name": g("VNAIMP", "vnaimp"),
            "short_name": g("VNAIMK", "vnaimk"),
            "registration_date": _parse_date(g("DREG", "dreg")),
            "inspectorate_code": g("NMNS", "nmns"),
            "inspectorate_name": g("VMNS", "vmns"),
            "status_code": g("CKODSOST", "ckodsost"),
            "status_date": _parse_date(g("DLIKV", "dlikv")),
            "address": format_grp_address(g("VPADRES", "vpadres")),
            "updated_at": datetime.now(),
        }
        stmt = pg_insert(GrpTaxpayerData).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[GrpTaxpayerData.unp],
            set_={
                field: getattr(stmt.excluded, field)
                for field in values
                if field != "unp"
            },
        )
        self.db.execute(stmt)
        
        # Обновить флаг парсинга в raw таблице
        raw_record.parsed = True
        raw_record.parsed_at = datetime.now()
        
        self.db.flush()
        return self.get_by_unp(unp)
    
    def parse_batch(self, limit: int = 100) -> Tuple[int, int]:
        """Распарсить пакет неспарсенных записей. Возвращает (успешно, ошибок)."""
        unparsed = self.get_unparsed_raw_data(limit=limit)
        
        success = 0
        errors = 0
        
        for raw_record in unparsed:
            try:
                with self.db.begin_nested():
                    parsed_record = self.parse_from_raw(raw_record.unp)
                if parsed_record is not None:
                    success += 1
            except Exception as e:
                errors += 1
                raw_record.last_error = f"Parse error: {str(e)}"
        
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return success, errors

    def reconcile_preserved_rows(self, limit: int = 1000) -> int:
        """Mark error-only raw rows as handled if parsed data already exists."""
        rows = (
            self.db.query(GrpRawData)
            .join(GrpTaxpayerData, GrpTaxpayerData.unp == GrpRawData.unp)
            .filter(GrpRawData.parsed == False)
            .order_by(GrpRawData.updated_at.asc())
            .limit(limit)
            .all()
        )

        reconciled = 0
        now = datetime.now()
        for row in rows:
            if row.raw_json:
                continue
            row.parsed = True
            row.parsed_at = now
            reconciled += 1

        if reconciled:
            self.db.commit()

        return reconciled
    
    def get_by_unp(self, unp: int) -> Optional[GrpTaxpayerData]:
        """Получить распарсенные данные по УНП."""
        return self.db.query(GrpTaxpayerData).filter(GrpTaxpayerData.unp == unp).first()

    def list_recent(self, limit: int = 100, offset: int = 0) -> List[GrpTaxpayerData]:
        """Получить последние распарсенные записи."""
        return (
            self.db.query(GrpTaxpayerData)
            .order_by(GrpTaxpayerData.updated_at.desc().nullslast())
            .offset(offset)
            .limit(limit)
            .all()
        )
    
    def reformat_addresses(self, limit: int = 1000) -> int:
        """Переформатировать адреса в существующих записях. Возвращает количество обновленных записей."""
        from sqlalchemy import text

        # Получить записи с адресами
        records = (
            self.db.query(GrpTaxpayerData)
            .filter(GrpTaxpayerData.address.isnot(None))
            .filter(GrpTaxpayerData.address != '')
            .limit(limit)
            .all()
        )

        updated_count = 0
        for record in records:
            formatted = format_grp_address(record.address)
            if formatted != record.address:
                record.address = formatted
                updated_count += 1

        if updated_count > 0:
            self.db.commit()

        return updated_count

    def count_stats(self) -> Dict[str, int]:
        """Статистика по таблицам ГРП."""
        return {
            "raw_total": self.db.query(func.count(GrpRawData.unp)).scalar() or 0,
            "raw_unparsed": self.db.query(func.count(GrpRawData.unp)).filter(GrpRawData.parsed == False).scalar() or 0,
            "parsed_total": self.db.query(func.count(GrpTaxpayerData.unp)).scalar() or 0,
        }
