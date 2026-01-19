"""Aggregator service - main orchestration service"""
from typing import Optional, Dict, Any
from datetime import datetime
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
            
            # 3. Save to DB
            raw_entry = self.db.query(RawCompanyData).filter(RawCompanyData.unp == unp).first()
            if raw_entry:
                raw_entry.data = raw_data
                raw_entry.updated_at = datetime.now()
                raw_entry.processed_at = None
            else:
                raw_entry = RawCompanyData(unp=unp, data=raw_data)
                self.db.add(raw_entry)
            
            self.db.commit()
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Raw save error {unp}: {e}")
            raise

    def process_raw_data(self, unp: int):
        """Parse JSON from DB into clean tables"""
        try:
            raw_entry = self.db.query(RawCompanyData).filter(RawCompanyData.unp == unp).first()
            if not raw_entry:
                logger.warning(f"No raw data found for {unp}")
                return

            db_structure = self.mapper.map_to_db_structure(unp, raw_entry.data)
            
            company_crud = CompanyCRUD(self.db)
            company_crud.save_full_company_data(db_structure)
            
            raw_entry.processed_at = datetime.now()
            raw_entry.last_error = None
            self.db.commit()
            
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
            company_crud = CompanyCRUD(self.db)
            
            # Check cache
            cached = company_crud.get_full_dossier(unp)
            if cached and use_cache:
                logger.info(f"Returning cached data for {unp}")
                return cached

            # Fetch fresh data
            success = await self.fetch_and_save_raw(unp)
            if success:
                self.process_raw_data(unp)
                return company_crud.get_full_dossier(unp)
        
        return None

    def close(self):
        """Close database connection"""
        self.db.close()

