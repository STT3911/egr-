#!/usr/bin/env python3
import logging
import time
from .database import Database
from .api_client import GIASAPIClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FixPlans:
    def __init__(self):
        self.db = Database()
        self.api = GIASAPIClient()

    def fix_company(self, unp: str):
        """Fix company name for specific UNP"""
        try:
            # Get latest plan for this UNP
            with self.db.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT uuid FROM gias_plans 
                    WHERE unp = %s 
                    ORDER BY dt_update DESC 
                    LIMIT 1
                """, (unp,))
                row = cursor.fetchone()

                if not row:
                    logger.warning(f"No plans found for UNP {unp}")
                    return False

                plan_uuid = row[0]

            # Get plan details
            plan_detail = self.api.get_plan_details(plan_uuid)
            if not plan_detail:
                logger.error(f"Failed to get plan details for {plan_uuid}")
                return False

            company_name = plan_detail.nameOfCompany
            logger.info(f"Updating company: {company_name} (UNP: {unp})")

            # Update company table
            with self.db.connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE gias_plans_companies 
                    SET company_name = %s 
                    WHERE unp = %s
                """, (company_name, unp))

                # Also update all plans with this UNP
                cursor.execute("""
                    UPDATE gias_plans 
                    SET name_of_company = %s 
                    WHERE unp = %s
                """, (company_name, unp))

                self.db.connection.commit()

            return True

        except Exception as e:
            logger.error(f"Error fixing company {unp}: {e}")
            self.db.connection.rollback()
            return False

    def run(self, batch_size: int = 25):
        """Run company fix process"""
        logger.info("Starting company fix process")

        try:
            while True:
                # Find companies with missing names
                with self.db.connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT unp FROM gias_plans_companies 
                        WHERE company_name IS NULL 
                        LIMIT %s
                    """, (batch_size,))

                    companies = cursor.fetchall()

                if not companies:
                    logger.info("No more companies to fix")
                    break

                logger.info(f"Fixing {len(companies)} companies")

                for row in companies:
                    unp = row[0]
                    self.fix_company(unp)
                    time.sleep(1)  # Delay to avoid rate limiting

                time.sleep(2)  # Small delay between batches

        except KeyboardInterrupt:
            logger.info("Company fix interrupted")
        except Exception as e:
            logger.error(f"Company fix error: {e}")
        finally:
            self.db.close()
            logger.info("Company fix completed")


if __name__ == "__main__":
    fixer = FixPlans()
    fixer.run()