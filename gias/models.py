from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum


class PlanState(str, Enum):
    ACTIVE = "ACTIVE"
    OLD = "OLD"
    PUBLISHED = "PUBLISHED"
    DRAFT = "DRAFT"


@dataclass
class PlanSearchItem:
    uuid: str
    dtCreate: int
    dtUpdate: int
    chainUuid: str
    authorUUID: Optional[str]
    state: str
    postDate: int
    version: int
    identificationNumber: str
    nameOfCompany: str
    unp: str
    year: int
    customer: Optional[str]


@dataclass
class ApproximateCost:
    budgetCost: float
    fundCost: float
    innerCost: float
    finYear: int


@dataclass
class PurchaseItem:
    id: str
    publicNumber: str
    goodsName: str
    okrb0081995Code: str
    okrb0081995Name: str
    okrb0072012Code: str
    okrb0072012Name: str
    unitCode: Optional[str]
    unitName: Optional[str]
    type: str
    approximateValue: float
    approximateCosts: List[ApproximateCost]
    procedureMonths: List[int]


@dataclass
class PlanDetail:
    uuid: str
    dtCreate: int
    dtUpdate: int
    chainUuid: str
    authorUUID: Optional[str]
    state: str
    postDate: int
    version: int
    identificationNumber: str
    nameOfCompany: str
    unp: str
    year: int
    approvePerson: str
    postPerson: str
    approveDate: Optional[int]
    purchases: List[PurchaseItem]


@dataclass
class SyncLog:
    id: Optional[int] = None
    sync_time: Optional[datetime] = None
    year: Optional[int] = None
    type: str = ""
    pages_processed: int = 0
    new_plans: int = 0
    updated_plans: int = 0
    new_items: int = 0
    updated_items: int = 0
    deleted_plans: int = 0
    duration_seconds: float = 0.0
    status: str = "success"
    error_message: Optional[str] = None