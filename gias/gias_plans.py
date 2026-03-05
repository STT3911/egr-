#!/usr/bin/env python3
import logging
import os
import time
from datetime import datetime
from typing import Optional
from .database import Database
from .api_client import GIASAPIClient
from .models import SyncLog

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GIASPlansIncremental:
    def __init__(self):
        self.db = Database()
        self.api = GIASAPIClient()
        self.max_updated_file = "max_date.ts"
        self.running = True

    def load_max_updated(self) -> Optional[datetime]:
        """Load max updated date from file"""
        try:
            if os.path.exists(self.max_updated_file):
                with open(self.max_updated_file, 'r') as f:
                    timestamp = int(f.read().strip())
                    return datetime.fromtimestamp(timestamp / 1000)
            return None
        except Exception as e:
            logger.error(f"Error loading max updated date: {e}")
            return None

    def save_max_updated(self, dt: datetime):
        """Save max updated date to file"""
        try:
            timestamp = int(dt.timestamp() * 1000)
            with open(self.max_updated_file, 'w') as f:
                f.write(str(timestamp))
        except Exception as e:
            logger.error(f"Error saving max updated date: {e}")

    def process_year(self, year: int, max_updated: Optional[datetime] = None):
        """Process plans for specific year incrementally"""
        logger.info(f"Starting incremental sync for year {year}")

        start_time = time.time()
        page = 0
        has_more = True
        plans_processed = 0
        items_processed = 0
        new_plans = 0
        updated_plans = 0
        existing_uuids = self.db.get_existing_plan_uuids(year)

        try:
            while has_more and self.running:
                logger.info(f"Processing page {page} for year {year}")

                # Search plans
                plans = self.api.search_plans(page=page, year=year)
                if not plans:
                    logger.info(f"No more plans found for year {year}")
                    break

                # Filter by max_updated if provided
                if max_updated:
                    # Convert max_updated to timestamp
                    max_updated_ts = int(max_updated.timestamp() * 1000)
                    plans = [p for p in plans if p.dtUpdate > max_updated_ts]

                    if not plans:
                        logger.info(f"No new plans after {max_updated}")
                        break

                for plan in plans:
                    try:
                        # Get plan details
                        plan_detail = self.api.get_plan_details(plan.uuid)
                        if not plan_detail:
                            logger.warning(f"Failed to get details for plan {plan.uuid}")
                            continue

                        # Convert timestamps
                        dt_create = datetime.fromtimestamp(plan_detail.dtCreate / 1000)
                        dt_update = datetime.fromtimestamp(plan_detail.dtUpdate / 1000)
                        post_date = datetime.fromtimestamp(plan_detail.postDate / 1000)
                        approve_date = datetime.fromtimestamp(
                            plan_detail.approveDate / 1000) if plan_detail.approveDate else None

                        # Save to database
                        success = self.db.save_plan(
                            plan_detail, dt_create, dt_update,
                            post_date, approve_date
                        )

                        if success:
                            plans_processed += 1
                            items_processed += len(plan_detail.purchases)

                            if plan.uuid in existing_uuids:
                                updated_plans += 1
                            else:
                                new_plans += 1
                                existing_uuids.add(plan.uuid)

                            # Update max_updated
                            if not max_updated or dt_update > max_updated:
                                max_updated = dt_update
                                self.save_max_updated(max_updated)

                        # Small delay to avoid rate limiting
                        time.sleep(0.1)

                    except Exception as e:
                        logger.error(f"Error processing plan {plan.uuid}: {e}")
                        continue

                # Check if we should continue
                page += 1

                # Check if we've reached plans older than max_updated
                if max_updated:
                    oldest_plan_ts = min(p.dtUpdate for p in plans)
                    if oldest_plan_ts <= int(max_updated.timestamp() * 1000):
                        logger.info(f"Reached plans older than max_updated for year {year}")
                        break

                # Check pagination
                if len(plans) < 50:  # Assuming page_size is 50
                    logger.info(f"No more plans for year {year}")
                    break

                # Small delay between pages
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("Sync interrupted by user")
            self.running = False
        except Exception as e:
            logger.error(f"Error processing year {year}: {e}")

        finally:
            duration = time.time() - start_time

            # Log sync results
            sync_log = SyncLog(
                year=year,
                type="incremental",
                pages_processed=page,
                new_plans=new_plans,
                updated_plans=updated_plans,
                new_items=items_processed,
                duration_seconds=duration,
                status="success" if self.running else "interrupted"
            )

            self.db.log_sync(sync_log)

            logger.info(f"Incremental sync for year {year} completed:")
            logger.info(f"  Duration: {duration:.2f} seconds")
            logger.info(f"  Pages processed: {page}")
            logger.info(f"  Plans processed: {plans_processed}")
            logger.info(f"  New plans: {new_plans}")
            logger.info(f"  Updated plans: {updated_plans}")
            logger.info(f"  Items processed: {items_processed}")

    def run(self):
        """Main loop for incremental sync"""
        logger.info("Starting incremental sync service")

        try:
            while self.running:
                # Load max updated date
                max_updated = self.load_max_updated()
                if max_updated:
                    logger.info(f"Resuming from {max_updated}")
                else:
                    logger.info("Starting fresh sync")

                # Get current year
                current_year = datetime.now().year

                # Process current and next year
                for year in [current_year - 1, current_year, current_year + 1]:
                    if not self.running:
                        break

                    self.process_year(year, max_updated)

                if not self.running:
                    break

                logger.info("Sleeping for 10 seconds before next iteration")
                time.sleep(10)

        except KeyboardInterrupt:
            logger.info("Service interrupted by user")
        except Exception as e:
            logger.error(f"Service error: {e}")
        finally:
            self.db.close()
            logger.info("Service stopped")


if __name__ == "__main__":
    sync = GIASPlansIncremental()
    sync.run()