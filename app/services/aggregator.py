"""Aggregator service - main orchestration service"""
import hashlib
import json
from typing import Optional, Dict, Any
from datetime import datetime


def _data_hash(data: dict | None) -> bytes | None:
    """MD5 fingerprint for change detection (not for security)."""
    if not data:
        return None
    return hashlib.md5(
        json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    ).digest()
from app.services.egr_client import EGRClient, MobileEGRClient
from app.services.mapper_service import CompanyMapper
from app.crud.company import CompanyCRUD
from app.core.config import settings
from app.core.database import SessionLocal
from app.database.models import RawCompanyData
from app.core.logger import get_logger

logger = get_logger("aggregator")


class AggregatorService:
    """Main service for aggregating EGR data"""
    
    def __init__(self):
        self.egr_client = EGRClient(settings.EGR_API_URL)
        self.mobile_client = MobileEGRClient(settings.EGR_MOBILE_API_URL) if settings.EGR_MOBILE_API_URL else None
        self.mapper = CompanyMapper()
        self.db = SessionLocal()
        self.redis = None
        try:
            import redis as redis_lib
            self.redis = redis_lib.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
                socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
                retry_on_timeout=False,
            )
        except Exception as e:
            logger.warning(f"Redis init error: {e}")
        
    async def fetch_and_save_raw(self, unp: int) -> bool:
        """Download JSON and save to DB. Priority: Legacy -> Mobile"""
        try:
            raw_data = None
            
            # 1. Try Legacy API first (has full data: addresses, VED, history)
            raw_data = await self.egr_client.get_full_company_history(unp)
            if raw_data:
                logger.info(f"Got data from Legacy API for {unp}")
            
            # 2. If Legacy didn't return data, try Mobile API (basic info only)
            if not raw_data and self.mobile_client:
                try:
                    common_info = await self.mobile_client.get_common_info(str(unp))
                    
                    if common_info:
                        # Mobile API doesn't reliably provide addresses via separate endpoint
                        raw_data = {
                            "common_info": common_info,
                            "place_location": None
                        }
                        logger.info(f"Got data from Mobile API for {unp} (basic info only)")
                except Exception as e:
                    logger.warning(f"Mobile API error for {unp}: {e}")
            
            if not raw_data:
                logger.warning(f"No data for {unp} in both APIs")
                return False

            self.save_raw_payload(unp, raw_data)
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Raw save error {unp}: {e}")
            raise

    def save_raw_payload(self, unp: int, raw_data: dict) -> RawCompanyData:
        """Persist an already fetched full EGR payload without another API request."""
        try:
            now = datetime.now()
            raw_entry = self.db.query(RawCompanyData).filter(RawCompanyData.unp == unp).first()
            if raw_entry:
                data_changed = _data_hash(raw_entry.data) != _data_hash(raw_data)
                if data_changed or raw_entry.processed_at is None:
                    raw_entry.data = raw_data
                    raw_entry.base_info = raw_data.get("base_info")
                    raw_entry.base_info_fetched_at = now
                    raw_entry.addresses = raw_data.get("addresses") or []
                    raw_entry.addresses_fetched_at = now
                    raw_entry.ved = raw_data.get("ved") or []
                    raw_entry.ved_fetched_at = now
                    raw_entry.names = raw_data.get("names") or []
                    raw_entry.names_fetched_at = now
                    raw_entry.updated_at = now
                    raw_entry.processed_at = None
                else:
                    raw_entry.updated_at = now
            else:
                raw_entry = RawCompanyData(
                    unp=unp,
                    data=raw_data,
                    base_info=raw_data.get("base_info"),
                    base_info_fetched_at=now,
                    addresses=raw_data.get("addresses") or [],
                    addresses_fetched_at=now,
                    ved=raw_data.get("ved") or [],
                    ved_fetched_at=now,
                    names=raw_data.get("names") or [],
                    names_fetched_at=now,
                )
                self.db.add(raw_entry)

            self.db.commit()
            return raw_entry

        except Exception as e:
            self.db.rollback()
            logger.error(f"Raw save error {unp}: {e}")
            raise

    def process_raw_data(self, unp: int, raw_entry=None):
        """Parse JSON from DB into clean tables.

        raw_entry можно передать заранее загруженным (из egr_process_raw),
        чтобы не делать повторный SELECT по UNP.
        """
        try:
            if raw_entry is None:
                raw_entry = self.db.query(RawCompanyData).filter(RawCompanyData.unp == unp).first()
            if not raw_entry:
                logger.warning(f"No raw data found for {unp}")
                return

            raw_data = raw_entry.get_data()
            if not raw_data:
                logger.warning(f"No raw data to parse for {unp}")
                return
            db_structure = self.mapper.map_to_db_structure(unp, raw_data)
            
            company_crud = CompanyCRUD(self.db)
            company_crud.save_full_company_data(db_structure)
            
            raw_entry.processed_at = datetime.now()
            raw_entry.last_error = None
            self.db.commit()

            # Индексацию НЕ делаем синхронно здесь: save_full_company_data уже поставил
            # компанию в search_index_queue, пачкой её обработает process_search_index_queue.
            # Это убирает обращение к ES из горячего пути обработки каждой строки.
            logger.info(f"Successfully processed {unp}")
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Processing error {unp}: {e}")
            try:
                raw_entry = self.db.query(RawCompanyData).filter(RawCompanyData.unp == unp).first()
                if raw_entry:
                    raw_entry.last_error = str(e)
                    self.db.commit()
            except:
                pass
            raise

    async def get_company_profile(self, identifier: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """Get company profile with optional cache"""
        if identifier.isdigit() and len(identifier) == 9:
            unp = int(identifier)
            cache_key = f"company_profile_v2:{unp}"

            # 1. Проверяем Redis (быстрее всего — 5-10мс)
            if use_cache:
                try:
                    if self.redis:
                        cached_raw = self.redis.get(cache_key)
                        if cached_raw:
                            logger.info(f"Redis cache hit for {unp}")
                            return json.loads(cached_raw)
                except Exception as e:
                    logger.warning(f"Redis error for {unp}: {e}")

            # 2. Проверяем БД (333мс)
            company_crud = CompanyCRUD(self.db)
            cached = company_crud.get_full_dossier(unp)
            if cached and use_cache:
                logger.info(f"DB cache hit for {unp}")
                # Сохраняем в Redis на 1 час
                try:
                    if self.redis:
                        self.redis.setex(cache_key, 3600, json.dumps(cached, default=str))
                except Exception as e:
                    logger.warning(f"Redis save error for {unp}: {e}")
                return cached

            # 3. Идём в ЕГР (медленно, только если нет в БД)
            success = await self.fetch_and_save_raw(unp)
            if success:
                self.process_raw_data(unp)
                profile = company_crud.get_full_dossier(unp)
                if profile:
                    try:
                        if self.redis:
                            self.redis.setex(cache_key, 3600, json.dumps(profile, default=str))
                    except Exception as e:
                        logger.warning(f"Redis save error for {unp}: {e}")
                return profile

        return None

    def close(self):
        """Close database connection"""
        self.db.close()
