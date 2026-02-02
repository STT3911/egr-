"""CRUD operations for GRP taxpayer data."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple, List

from dateutil.parser import parse as dt_parse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database.models import GrpTaxpayerData, GrpRawData


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
            record = GrpRawData(unp=unp)
            self.db.add(record)
        
        record.raw_json = raw_json or {}
        record.http_status = http_status
        record.last_error = error
        record.updated_at = datetime.now()
        record.parsed = False  # Сбросить флаг при обновлении сырых данных
        record.parsed_at = None
        
        self.db.flush()
        return record
    
    def get_raw_by_unp(self, unp: int) -> Optional[GrpRawData]:
        """Получить сырые данные по УНП."""
        return self.db.query(GrpRawData).filter(GrpRawData.unp == unp).first()
    
    def get_unparsed_raw_data(self, limit: int = 100) -> List[GrpRawData]:
        """Получить неспарсенные сырые данные."""
        return (
            self.db.query(GrpRawData)
            .filter(GrpRawData.parsed == False)
            .filter(GrpRawData.raw_json != None)
            .order_by(GrpRawData.fetched_at.asc())
            .limit(limit)
            .all()
        )

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
        
        # Получить или создать запись в grp_taxpayer_data
        parsed_record = self.db.query(GrpTaxpayerData).filter(GrpTaxpayerData.unp == unp).first()
        if not parsed_record:
            parsed_record = GrpTaxpayerData(unp=unp)
            self.db.add(parsed_record)
        
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
        
        parsed_record.full_name = g("VNAIMP", "vnaimp")
        parsed_record.short_name = g("VNAIMK", "vnaimk")
        parsed_record.registration_date = _parse_date(g("DREG", "dreg"))
        parsed_record.inspectorate_code = g("NMNS", "nmns")
        parsed_record.inspectorate_name = g("VMNS", "vmns")
        parsed_record.status_code = g("CKODSOST", "ckodsost")
        parsed_record.status_date = _parse_date(g("DLIKV", "dlikv"))
        parsed_record.address = g("VPADRES", "vpadres")
        parsed_record.updated_at = datetime.now()
        
        # Обновить флаг парсинга в raw таблице
        raw_record.parsed = True
        raw_record.parsed_at = datetime.now()
        
        self.db.flush()
        return parsed_record
    
    def parse_batch(self, limit: int = 100) -> Tuple[int, int]:
        """Распарсить пакет неспарсенных записей. Возвращает (успешно, ошибок)."""
        unparsed = self.get_unparsed_raw_data(limit=limit)
        
        success = 0
        errors = 0
        
        for raw_record in unparsed:
            try:
                self.parse_from_raw(raw_record.unp)
                success += 1
            except Exception as e:
                errors += 1
                # Можно логировать ошибку
                raw_record.last_error = f"Parse error: {str(e)}"
        
        self.db.commit()
        return success, errors
    
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
    
    def count_stats(self) -> Dict[str, int]:
        """Статистика по таблицам ГРП."""
        return {
            "raw_total": self.db.query(func.count(GrpRawData.unp)).scalar() or 0,
            "raw_unparsed": self.db.query(func.count(GrpRawData.unp)).filter(GrpRawData.parsed == False).scalar() or 0,
            "parsed_total": self.db.query(func.count(GrpTaxpayerData.unp)).scalar() or 0,
        }