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


def get_raw_count_needing_enrichment():
    """Количество записей в raw_data с processed_at=None (ждут обогащения или парсинга)."""
    try:
        db = SessionLocal()
        # RawCompanyData.data is JSONB; need enrichment if missing keys
        count = db.query(RawCompanyData).filter(
            RawCompanyData.processed_at.is_(None)
        ).count()
        db.close()
        return count
    except Exception as e:
        logger.error(f"Error counting raw data: {e}")
        return 0

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
    
    # Импортировать: 3 шага (JSON -> raw_data -> обогащение API -> структурные таблицы)
    logger.info("🚀 Starting 3-step import process...")
    logger.info("")
    try:
        from app.tasks.sync_tasks import load_companies_from_json, enrich_missing_raw, process_pending_raw
        
        # Step 1: Load base_info from JSON files into raw_data
        logger.info("📥 STEP 1/3: Loading base data from JSON files...")
        processed_step1 = load_companies_from_json()
        raw_total = get_raw_count_needing_enrichment()
        # Если в JSON только base_info, processed_step1 может быть 0 — это нормально
        if raw_total == 0 and (not processed_step1 or processed_step1 == 0):
            logger.warning("⚠️  No data in JSON or directory data/egr_json_full/ is empty")
            return False
        logger.info(f"✅ Step 1 complete: {processed_step1} processed from JSON, {raw_total} in raw_data (pending enrichment)")
        logger.info("")
        
        # Лимит для шагов 2 и 3: все необработанные или разумный максимум за один запуск
        limit = min(raw_total, 50_000) if raw_total else 10_000
        
        # Step 2: Enrich with full data from EGR API
        logger.info("📥 STEP 2/3: Enriching data from EGR API...")
        logger.info("   (This may take a while for large datasets)")
        enriched = enrich_missing_raw(limit=limit)
        logger.info(f"✅ Step 2 complete: {enriched} companies enriched")
        logger.info("")
        
        # Step 3: Process into structured tables
        logger.info("⚙️  STEP 3/3: Processing into structured tables...")
        processed = process_pending_raw(limit=limit)
        logger.info(f"✅ Step 3 complete: {processed} companies processed")
        logger.info("")
        
        if processed > 0:
            logger.info(f"🎉 Auto-import completed successfully!")
            logger.info(f"   Total: {processed} companies ready to use")
            return True
        if enriched > 0:
            logger.info("   Enriched but not yet processed. Run again or: process_pending_raw(limit=...)")
            return True
        logger.warning("⚠️  Import run complete; no new companies processed (may need more enrich/process runs)")
        return True
            
    except Exception as e:
        logger.error(f"❌ Auto-import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = auto_import()
    sys.exit(0 if success else 1)
