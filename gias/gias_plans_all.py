#!/usr/bin/env python3
import logging
import time
import os
from datetime import datetime
from .database import Database
from .api_client import GIASAPIClient
from .models import SyncLog

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GIASPlansFull:
    def __init__(self):
        self.db = Database()
        self.api = GIASAPIClient()
        self.skip_list_file = "skip_list.txt"

    def load_skip_list(self) -> set:
        """Load list of already processed UUIDs"""
        skip_list = set()
        try:
            if os.path.exists(self.skip_list_file):
                with open(self.skip_list_file, 'r') as f:
                    for line in f:
                        uuid = line.strip()
                        if uuid:
                            skip_list.add(uuid)
        except Exception as e:
            logger.error(f"Error loading skip list: {e}")
        return skip_list

    def save_to_skip_list(self, uuid: str):
        """Save UUID to skip list"""
        try:
            with open(self.skip_list_file, 'a') as f:
                f.write(f"{uuid}\n")
        except Exception as e:
            logger.error(f"Error saving to skip list: {e}")

    def process_year(self, year: int):
        """Process all plans for specific year"""
        logger.info(f"Starting full sync for year {year}")

        start_time = time.time()
        skip_list = self.load_skip_list()
        existing_uuids = self.db.get_existing_plan_uuids(year)

        # Get total pages
        pagination = self.api.get_pagination_info(year=year)
        total_pages = pagination.get("totalPages", 0)
        total_elements = pagination.get("totalElements", 0)

        logger.info(f"Year {year}: {total_elements} plans, {total_pages} pages")

        page = 0
        plans_processed = 0
        items_processed = 0
        new_plans = 0
        updated_plans = 0
        processed_uuids = set(existing_uuids)

        try:
            while page < total_pages:
                logger.info(f"Processing page {page + 1}/{total_pages} for year {year}")

                # Search plans
                plans = self.api.search_plans(page=page, year=year)
                if not plans:
                    logger.warning(f"No plans on page {page}")
                    break

                for plan in plans:
                    # Skip if already processed
                    if plan.uuid in skip_list:
                        logger.debug(f"Skipping already processed plan {plan.uuid}")
                        continue

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

                            # Add to skip list
                            self.save_to_skip_list(plan.uuid)

                            # Check if this is new or updated
                            if plan.uuid in processed_uuids:
                                updated_plans += 1
                            else:
                                new_plans += 1
                                processed_uuids.add(plan.uuid)

                        # Small delay to avoid rate limiting
                        time.sleep(0.1)

                    except Exception as e:
                        logger.error(f"Error processing plan {plan.uuid}: {e}")
                        continue

                page += 1

                # Small delay between pages
                if page < total_pages:
                    time.sleep(1)

        except KeyboardInterrupt:
            logger.info("Sync interrupted by user")
        except Exception as e:
            logger.error(f"Error processing year {year}: {e}")

        finally:
            duration = time.time() - start_time

            # Log sync results
            sync_log = SyncLog(
                year=year,
                type="full",
                pages_processed=page,
                new_plans=new_plans,
                updated_plans=updated_plans,
                new_items=items_processed,
                duration_seconds=duration,
                status="success"
            )

            self.db.log_sync(sync_log)

            logger.info(f"Full sync for year {year} completed:")
            logger.info(f"  Duration: {duration:.2f} seconds")
            logger.info(f"  Pages processed: {page}")
            logger.info(f"  Plans processed: {plans_processed}")
            logger.info(f"  New plans: {new_plans}")
            logger.info(f"  Updated plans: {updated_plans}")
            logger.info(f"  Items processed: {items_processed}")

    def run(self, years: list = None, loop: bool = True, interval_seconds: int = 3600):
        """Run full sync for specified years, optionally looping with delay (default: hourly)"""
        if years is None:
            env_years = os.getenv("GIAS_SYNC_YEARS")
            if env_years:
                years = [int(y.strip()) for y in env_years.split(",") if y.strip()]
            else:
                years = [2026]  # default target year

        logger.info(f"Starting full sync for years: {years}")
        logger.info(f"Loop mode: {'on' if loop else 'off'}, interval: {interval_seconds} sec")

        try:
            while True:
                for year in years:
                    self.process_year(year)

                if not loop or interval_seconds <= 0:
                    break

                logger.info(f"Sleeping for {interval_seconds} seconds before next full sync")
                time.sleep(interval_seconds)

        except KeyboardInterrupt:
            logger.info("Full sync interrupted")
        except Exception as e:
            logger.error(f"Full sync error: {e}")
        finally:
            self.db.close()
            logger.info("Full sync completed")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='GIAS Full Sync')
    parser.add_argument('--years', type=str, help='Comma-separated list of years')
    default_loop = os.getenv("GIAS_FULL_SYNC_LOOP", "true").lower() not in ("0", "false", "no", "off")
    default_interval = int(os.getenv("GIAS_FULL_SYNC_INTERVAL", "3600"))
    parser.add_argument('--loop', dest='loop', action='store_true', default=default_loop, help='Run in loop mode (default from env GIAS_FULL_SYNC_LOOP=true)')
    parser.add_argument('--no-loop', dest='loop', action='store_false', help='Run once and exit')
    parser.add_argument('--interval', type=int, default=default_interval, help='Seconds between runs in loop mode (env GIAS_FULL_SYNC_INTERVAL)')
    args = parser.parse_args()

    if args.years:
        years = [int(y.strip()) for y in args.years.split(',')]
    else:
        years = None

    sync = GIASPlansFull()
    sync.run(years, loop=args.loop, interval_seconds=args.interval)