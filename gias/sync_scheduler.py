import schedule
import time
import logging
import os
from datetime import datetime
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
def run_full_sync():
    from .gias_plans_all import GIASPlansFull
    sync = GIASPlansFull()
    years = [2026]
    sync.run(years)
def run_incremental_sync():
    from .gias_plans import GIASPlansIncremental
    sync = GIASPlansIncremental()
    sync.run()
def main():
    full_sync_schedule = os.getenv('GIAS_FULL_SYNC_SCHEDULE', '0 3 * * *')
    schedule.every().day.at("03:00").do(run_full_sync)
    # Инкрементальный воркер запускается как отдельный сервис (бесконечный цикл),
    # поэтому его не планируем через schedule, чтобы не плодить параллельные инстансы.
    logger.info("Scheduler started. Full sync at 3:00 daily. Run incremental service separately.")
    while True:
        schedule.run_pending()
        time.sleep(60)
if __name__ == "__main__":
    main()