#!/usr/bin/env python3
"""
Автоматический импорт и парсинг данных из JSON файлов при запуске
"""
import sys
import os
import time
from pathlib import Path

# Добавить путь к приложению
sys.path.insert(0, '/app')

from app.core.database import SessionLocal
from app.database.models import RawCompanyData
from app.services.aggregator import AggregatorService
from app.core.logger import logger

def wait_for_db(max_attempts=30):
    """Ждать пока БД будет доступна"""
    from sqlalchemy import text
    
    logger.info("⏳ Waiting for database...")
    for attempt in range(max_attempts):
        try:
            db = SessionLocal()
            db.execute(text("SELECT 1"))
            db.close()
            logger.info("✅ Database is ready!")
            return True
        except Exception as e:
            logger.info(f"   Attempt {attempt + 1}/{max_attempts}: Database not ready yet...")
            time.sleep(2)
    
    logger.error("❌ Database is not available after {max_attempts} attempts")
    return False

def check_if_data_exists():
    """Проверить есть ли уже данные в БД"""
    try:
        db = SessionLocal()
        count = db.query(RawCompanyData).count()
        db.close()
        return count > 0
    except Exception as e:
        logger.error(f"Error checking data: {e}")
        return False

def auto_import():
    """Автоматический импорт данных"""
    logger.info("╔════════════════════════════════════════════════════════╗")
    logger.info("║     AUTO-IMPORT: Starting automatic data import       ║")
    logger.info("╚════════════════════════════════════════════════════════╝")
    
    # Проверить что БД доступна
    if not wait_for_db():
        logger.error("❌ Cannot connect to database, skipping import")
        return False
    
    # Проверить есть ли уже данные
    if check_if_data_exists():
        logger.info("ℹ️  Data already exists in database, skipping import")
        logger.info("   To force reimport, clear the database first")
        return True
    
    # Импортировать через Celery задачу
    logger.info("🚀 Starting 3-step import process...")
    logger.info("")
    try:
        from app.tasks.sync_tasks import load_companies_from_json, enrich_missing_raw, process_pending_raw
        
        # Step 1: Load base_info from JSON files
        logger.info("📥 STEP 1/3: Loading base data from JSON files...")
        loaded = load_companies_from_json()
        if not loaded or loaded == 0:
            logger.warning("⚠️  No data was loaded from JSON files")
            return False
        logger.info(f"✅ Step 1 complete: {loaded} companies loaded to raw_data")
        logger.info("")
        
        # Step 2: Enrich with full data from API
        logger.info("📥 STEP 2/3: Enriching data from EGR API...")
        logger.info("   (This may take a while for large datasets)")
        enriched = enrich_missing_raw(limit=loaded)
        logger.info(f"✅ Step 2 complete: {enriched}/{loaded} companies enriched")
        logger.info("")
        
        # Step 3: Process into structured tables
        logger.info("⚙️  STEP 3/3: Processing into structured tables...")
        processed = process_pending_raw(limit=loaded)
        logger.info(f"✅ Step 3 complete: {processed} companies processed")
        logger.info("")
        
        if processed > 0:
            logger.info(f"🎉 Auto-import completed successfully!")
            logger.info(f"   Total: {processed} companies ready to use")
            return True
        else:
            logger.warning("⚠️  Import completed but no data was processed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Auto-import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = auto_import()
    sys.exit(0 if success else 1)
