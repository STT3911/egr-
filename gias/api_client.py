import requests
import logging
from typing import List, Dict, Any, Optional
from .models import PlanSearchItem, PlanDetail, PurchaseItem, ApproximateCost
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class GIASAPIClient:
    def __init__(self, base_url: str = "https://gias.by"):
        self.base_url = base_url
        self.session = requests.Session()
        # Retry on transient connection resets/5xx from remote host.
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods={"GET", "POST"},
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json"
        })

    def search_plans(self, page: int = 0, page_size: int = 50,
                     year: int = 2026, sort_field: str = "dtUpdate",
                     sort_order: str = "DESC") -> List[PlanSearchItem]:
        """Search for plans"""
        url = f"{self.base_url}/search/api/v1/search/plans"
        payload = {
            "page": page,
            "pageSize": page_size,
            "sortField": sort_field,
            "sortOrder": sort_order,
            "year": year
        }

        try:
            response = self.session.post(url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()

            plans = []
            for item in data.get("content", []):
                plan = PlanSearchItem(
                    uuid=item["uuid"],
                    dtCreate=item["dtCreate"],
                    dtUpdate=item["dtUpdate"],
                    chainUuid=item["chainUuid"],
                    authorUUID=item.get("authorUUID"),
                    state=item["state"],
                    postDate=item["postDate"],
                    version=item["version"],
                    identificationNumber=item["identificationNumber"],
                    nameOfCompany=item["nameOfCompany"],
                    unp=item["unp"],
                    year=item["year"],
                    customer=item.get("customer")
                )
                plans.append(plan)

            return plans

        except Exception as e:
            logger.error(f"Error searching plans: {e}")
            return []

    def get_plan_details(self, plan_uuid: str) -> Optional[PlanDetail]:
        """Get detailed plan information"""
        url = f"{self.base_url}/plan/api/v1/plans/{plan_uuid}"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Parse purchases
            purchases = []
            for purchase_data in data.get("purchases", []):
                # Parse approximate costs
                approximate_costs = []
                for cost_data in purchase_data.get("approximateCosts", []):
                    cost = ApproximateCost(
                        budgetCost=cost_data.get("budgetCost", 0),
                        fundCost=cost_data.get("fundCost", 0),
                        innerCost=cost_data.get("innerCost", 0),
                        finYear=cost_data.get("finYear", 0)
                    )
                    approximate_costs.append(cost)

                purchase = PurchaseItem(
                    id=purchase_data["id"],
                    publicNumber=purchase_data["publicNumber"],
                    goodsName=purchase_data["goodsName"],
                    okrb0081995Code=purchase_data["okrb0081995Code"],
                    okrb0081995Name=purchase_data["okrb0081995Name"],
                    okrb0072012Code=purchase_data["okrb0072012Code"],
                    okrb0072012Name=purchase_data["okrb0072012Name"],
                    unitCode=purchase_data.get("unitCode") or purchase_data.get("unit"),
                    unitName=purchase_data.get("unitName"),
                    type=purchase_data["type"],
                    approximateValue=purchase_data["approximateValue"],
                    approximateCosts=approximate_costs,
                    procedureMonths=purchase_data.get("procedureMonths", [])
                )
                purchases.append(purchase)

            plan = PlanDetail(
                uuid=data["uuid"],
                dtCreate=data["dtCreate"],
                dtUpdate=data["dtUpdate"],
                chainUuid=data["chainUuid"],
                authorUUID=data.get("authorUUID"),
                state=data["state"],
                postDate=data["postDate"],
                version=data["version"],
                identificationNumber=data["identificationNumber"],
                nameOfCompany=data["nameOfCompany"],
                unp=data["unp"],
                year=data["year"],
                approvePerson=data.get("approvePerson", ""),
                postPerson=data.get("postPerson", ""),
                approveDate=data.get("approveDate"),
                purchases=purchases
            )

            return plan

        except Exception as e:
            logger.error(f"Error getting plan details {plan_uuid}: {e}")
            return None

    def get_pagination_info(self, page: int = 0, page_size: int = 50,
                            year: int = 2026) -> Dict[str, Any]:
        """Get pagination information"""
        url = f"{self.base_url}/search/api/v1/search/plans"
        payload = {
            "page": page,
            "pageSize": page_size,
            "sortField": "dtUpdate",
            "sortOrder": "DESC",
            "year": year
        }

        try:
            response = self.session.post(url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()

            return {
                "totalPages": data.get("totalPages", 0),
                "totalElements": data.get("totalElements", 0),
                "number": data.get("number", 0),
                "size": data.get("size", 0)
            }

        except Exception as e:
            logger.error(f"Error getting pagination info: {e}")
            return {}