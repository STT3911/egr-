"""Script to trigger initial data seeding"""
import sys
import asyncio
from datetime import date, datetime
from app.core.logger import get_logger
from app.tasks.sync_tasks import process_period_range

logger = get_logger("init_seed")


def seed_specific_period(start_date: str, end_date: str):
    """
    Seed data for a specific period
    
    This will:
    1. Fetch all companies registered in the period (getBaseInfoByPeriod)
    2. Fetch all events that occurred in the period (getEventByPeriod)
    3. Download full data for each unique company
    
    Format: DD.MM.YYYY
    Example: python init_seed.py 01.01.2022 31.01.2022
    """
    logger.info(f"🚀 Starting seed for period: {start_date} - {end_date}")
    logger.info("📋 This will fetch:")
    logger.info("   1️⃣  Companies registered in this period")
    logger.info("   2️⃣  Events that occurred in this period")
    logger.info("   3️⃣  Full details for all unique companies")
    
    # Validate dates
    try:
        start = datetime.strptime(start_date, "%d.%m.%Y")
        end = datetime.strptime(end_date, "%d.%m.%Y")
        
        if start > end:
            logger.error("❌ Start date must be before end date")
            sys.exit(1)
            
        if start < datetime(1991, 1, 1):
            logger.error("❌ Start date cannot be before 1991-01-01")
            sys.exit(1)
            
        if end > datetime.now():
            logger.error("❌ End date cannot be in the future")
            sys.exit(1)
    
    except ValueError as e:
        logger.error(f"❌ Invalid date format: {e}")
        logger.error("Expected format: DD.MM.YYYY (e.g., 01.01.2022)")
        sys.exit(1)
    
    # Trigger processing
    logger.info(f"📊 Triggering Celery task for {start_date} - {end_date}")
    result = process_period_range.delay(start_date, end_date)
    
    logger.info(f"✅ Task queued with ID: {result.id}")
    logger.info("💡 Monitor progress in celery worker logs:")
    logger.info(f"   docker-compose logs -f egr_celery_worker")


def seed_january_2022():
    """Seed January 2022 (good test period)"""
    logger.info("🚀 Seeding January 2022...")
    seed_specific_period("01.01.2022", "31.01.2022")


def seed_full_history():
    """Seed full history from 1991 to today (SLOW!)"""
    logger.warning("⚠️  WARNING: Full history seeding will take VERY LONG TIME!")
    logger.warning("   This will process 30+ years of data")
    logger.warning("   Consider using specific period instead")
    
    response = input("Continue with full history? (yes/no): ")
    if response.lower() != "yes":
        logger.info("Cancelled")
        sys.exit(0)
    
    from app.tasks.sync_tasks import initial_seed_by_history
    
    logger.info("🚀 Starting full history seed...")
    result = initial_seed_by_history.delay()
    
    logger.info(f"✅ Task queued with ID: {result.id}")
    logger.info("💡 This will create many sub-tasks. Monitor:")
    logger.info(f"   docker-compose logs -f egr_celery_worker")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("=" * 60)
        print("🌱 EGR Data Seeding Script")
        print("=" * 60)
        print()
        print("Usage:")
        print("  1. Seed specific period:")
        print("     python init_seed.py <start_date> <end_date>")
        print("     Example: python init_seed.py 01.01.2022 31.01.2022")
        print()
        print("  2. Seed January 2022 (test):")
        print("     python init_seed.py --test")
        print()
        print("  3. Seed full history (SLOW!):")
        print("     python init_seed.py --full")
        print()
        print("=" * 60)
        sys.exit(0)
    
    if sys.argv[1] == "--test":
        seed_january_2022()
    elif sys.argv[1] == "--full":
        seed_full_history()
    elif len(sys.argv) == 3:
        seed_specific_period(sys.argv[1], sys.argv[2])
    else:
        print("❌ Invalid arguments. Run without arguments to see usage.")
        sys.exit(1)

