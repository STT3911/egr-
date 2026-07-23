"""
====================================================================
ВНЕШНИЙ СТАБИЛЬНЫЙ API  (для прод-интеграций, напр. tenders.by)
====================================================================
GET /api/v1/stable/companies/{unp}

НАЗНАЧЕНИЕ:
  Отдельный «замороженный» эндпоинт с фиксированным контрактом ответа
  (схема StableCompanyV1). Его выдача НЕ меняется при доработках сайта.

ПРАВИЛА (важно):
  • НЕ использовать на сайте.
  • НЕ менять структуру ответа без явного согласования с Anton.
  • Данные собираются здесь явным маппингом из БД, а НЕ через общий
    профиль сайта — чтобы изменения сайта не «протекали» наружу.

Авторизация: Bearer-токен PUBLIC_API_TOKEN (отдельный внешний токен).
====================================================================
"""
import hmac

from fastapi import APIRouter, Depends, HTTPException, Path, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.logger import get_logger
from app.database.models import Company, ReferenceStatus, CompanyPlaceLocation
from app.services.grp_discovery import discover_company_from_grp
from app.schemas.stable_company import (
    StableCompanyV1,
    StableAddressV1,
    StableVedV1,
    StableContactV1,
)

router = APIRouter()
logger = get_logger("api.stable")

_bearer = HTTPBearer(auto_error=False)


async def verify_stable_token(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
):
    """Отдельный Bearer-токен STABLE_API_TOKEN — только для этого эндпоинта."""
    if (
        not settings.STABLE_API_TOKEN
        or not credentials
        or not hmac.compare_digest(credentials.credentials, settings.STABLE_API_TOKEN)
    ):
        raise HTTPException(
            status_code=401,
            detail="Неверный или отсутствующий токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


@router.get("/companies/{unp}", response_model=StableCompanyV1)
async def get_stable_company(
    unp: str = Path(..., regex=r"^\d{9}$", description="УНП (9 цифр)"),
    db: Session = Depends(get_db),
    token: str = Depends(verify_stable_token),
):
    """Текущие данные по компании (без истории), стабильный контракт."""
    try:
        company = (
            db.query(Company)
            .options(
                selectinload(Company.names_history),
                selectinload(Company.addresses_history),
                selectinload(Company.ved_history),
                selectinload(Company.contacts_history),
            )
            .filter(Company.unp == int(unp))
            .first()
        )
        if not company:
            logger.info("Stable API DB miss for %s; trying GRP discovery", unp)
            await discover_company_from_grp(db, int(unp))
            company = (
                db.query(Company)
                .options(
                    selectinload(Company.names_history),
                    selectinload(Company.addresses_history),
                    selectinload(Company.ved_history),
                    selectinload(Company.contacts_history),
                )
                .filter(Company.unp == int(unp))
                .first()
            )
        if not company:
            raise HTTPException(status_code=404, detail=f"Компания {unp} не найдена")

        current_name = next(
            (n for n in sorted(company.names_history, key=lambda n: n.valid_to is None, reverse=True)),
            None,
        )
        current_address = next(
            (a for a in sorted(company.addresses_history, key=lambda a: a.valid_to is None, reverse=True)),
            None,
        )
        current_ved = [v for v in company.ved_history if v.valid_to is None]
        current_contacts = [c for c in company.contacts_history if c.valid_to is None]

        place = db.query(CompanyPlaceLocation).filter(CompanyPlaceLocation.unp == int(unp)).first()

        status_name = None
        if company.current_status_code:
            status = db.query(ReferenceStatus).filter(ReferenceStatus.id == company.current_status_code).first()
            status_name = status.name if status else None

        return StableCompanyV1(
            unp=company.unp,
            current_status_code=company.current_status_code,
            current_status_name=status_name,
            registration_date=company.registration_date.isoformat() if company.registration_date else None,
            liquidation_date=company.liquidation_date.isoformat() if company.liquidation_date else None,
            current_name_ru=current_name.full_name_ru if current_name else None,
            current_short_name_ru=current_name.short_name_ru if current_name else None,
            current_name_by=current_name.full_name_by if current_name else None,
            place_location_address=place.address if place else None,
            addresses=(
                [StableAddressV1(
                    full_address=current_address.full_address,
                    postal_code=current_address.postal_code,
                    region=current_address.region,
                    district=current_address.district,
                    valid_from=current_address.valid_from.isoformat() if current_address.valid_from else None,
                    valid_to=None,
                )] if current_address else []
            ),
            ved=[
                StableVedV1(
                    ved_code=v.ved_code,
                    ved_name=v.ved_name,
                    valid_from=v.valid_from.isoformat() if v.valid_from else None,
                    valid_to=None,
                )
                for v in current_ved
            ],
            contacts=[
                StableContactV1(email=c.email, website=c.website, phone=c.phone, fax=c.fax)
                for c in current_contacts
            ],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stable API error for {unp}: {e}")
        raise HTTPException(status_code=500, detail="internal error")
