"""
====================================================================
ЗАМОРОЖЕННЫЙ КОНТРАКТ ВНЕШНЕГО API  (stable company v1)
====================================================================
Эта схема обслуживает внешних потребителей (прод tenders.by).

ПРАВИЛА:
  • НЕ менять структуру/имена/типы полей без явного согласования с Anton.
  • НЕ использовать на сайте (у сайта своя схема CompanyProfileResponse).
  • Любые изменения сайта НЕ должны затрагивать этот файл.
  • Нужны новые поля внешним клиентам — добавлять опционально (в конец),
    не удаляя и не переименовывая существующие.

Версионирование: при несовместимом изменении делать v2 (новый файл/путь),
а v1 оставлять прежним.
====================================================================
"""
from typing import List, Optional

from pydantic import BaseModel


class StableAddressV1(BaseModel):
    full_address: Optional[str] = None
    postal_code: Optional[int] = None
    region: Optional[str] = None
    district: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None


class StableVedV1(BaseModel):
    ved_code: Optional[str] = None
    ved_name: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None


class StableContactV1(BaseModel):
    email: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None


class StableCompanyV1(BaseModel):
    unp: int
    current_status_code: Optional[int] = None
    current_status_name: Optional[str] = None
    registration_date: Optional[str] = None
    liquidation_date: Optional[str] = None
    current_name_ru: Optional[str] = None
    current_short_name_ru: Optional[str] = None
    current_name_by: Optional[str] = None
    place_location_address: Optional[str] = None
    addresses: List[StableAddressV1] = []
    ved: List[StableVedV1] = []
    contacts: List[StableContactV1] = []
