"""Company endpoints"""
from fastapi import APIRouter, HTTPException, Query, Path, Depends
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.schemas.company import CompanyProfileResponse, CompanyLookupResponse
from app.services.aggregator import AggregatorService
from app.core.config import settings
from app.services.egr_client import EGRClient, MobileEGRClient
from app.core.logger import get_logger
from app.core.database import get_db

logger = get_logger("api.companies")
router = APIRouter()


@router.get("/lookup", response_model=CompanyLookupResponse)
async def lookup_companies(
    q: str = Query(..., min_length=1, description="Поиск по УНП или названию"),
    limit: int = Query(10, ge=1, le=50, description="Максимум результатов"),
    db: Session = Depends(get_db),
):
    """
    Автокомплит по УНП или названию компании.
    """
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Параметр 'q' не может быть пустым")

    is_digit = query.isdigit()
    unp_prefix = f"{query}%" if is_digit else None
    name_term = f"%{query}%"

    sql = text("""
        SELECT
            c.unp,
            n.full_name_ru,
            n.short_name_ru,
            n.full_name_by
        FROM egr_companies c
        LEFT JOIN LATERAL (
            SELECT
                n.full_name_ru,
                n.short_name_ru,
                n.full_name_by,
                n.valid_from,
                n.valid_to
            FROM egr_company_names_history n
            WHERE n.company_id = c.id
            ORDER BY
                (n.valid_to IS NULL) DESC,
                n.valid_to DESC NULLS LAST,
                n.valid_from DESC NULLS LAST
            LIMIT 1
        ) n ON true
        WHERE (
            (:unp_prefix IS NOT NULL AND c.unp::text ILIKE :unp_prefix)
            OR (n.full_name_ru ILIKE :name_term)
            OR (n.short_name_ru ILIKE :name_term)
            OR (n.full_name_by ILIKE :name_term)
        )
        ORDER BY
            CASE WHEN :is_digit THEN (c.unp::text ILIKE :unp_prefix)::int ELSE 0 END DESC,
            c.unp
        LIMIT :limit
    """)

    rows = db.execute(sql, {
        "unp_prefix": unp_prefix,
        "name_term": name_term,
        "limit": limit,
        "is_digit": is_digit,
    }).mappings().all()

    results = []
    for row in rows:
        name = row["full_name_ru"] or row["short_name_ru"] or row["full_name_by"]
        results.append({
            "unp": int(row["unp"]),
            "name": name,
            "full_name_ru": row["full_name_ru"],
            "short_name_ru": row["short_name_ru"],
            "full_name_by": row["full_name_by"],
        })

    return {
        "query": query,
        "count": len(results),
        "results": results,
    }


@router.get("/{identifier}", response_model=CompanyProfileResponse)
async def get_company_profile(
    identifier: str = Path(..., regex=r'^\d{9}$', description="УНП или PAN (9 цифр)"),
    force_refresh: bool = Query(False, description="Принудительное обновление данных"),
    use_mobile_api: Optional[bool] = Query(None, description="Использовать мобильный API")
):
    """
    Получить профиль компании или ИП по УНП/PAN
    """
    try:
        aggregator = AggregatorService()
        
        # Check if mobile API is configured
        if use_mobile_api and not settings.EGR_MOBILE_API_URL:
            raise HTTPException(
                status_code=400,
                detail="Мобильный API не настроен"
            )
        
        # Get profile
        profile = await aggregator.get_company_profile(
            identifier=identifier,
            use_cache=not force_refresh
        )
        
        if not profile:
            raise HTTPException(
                status_code=404,
                detail=f"Компания с идентификатором {identifier} не найдена"
            )
        
        aggregator.close()
        return CompanyProfileResponse(**profile)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting company profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{identifier}/raw")
async def get_raw_data(
    identifier: str = Path(..., regex=r'^\d{9}$'),
    api_type: str = Query("auto", description="Тип API: mobile, legacy, auto")
):
    """Получить сырые данные из API ЕГР"""
    try:
        raw_data = {}
        
        # Get data from mobile API
        if api_type in ['mobile', 'auto'] and settings.EGR_MOBILE_API_URL:
            try:
                mobile_client = MobileEGRClient(settings.EGR_MOBILE_API_URL)
                raw_data['mobile_api'] = {
                    'common_info': await mobile_client.get_common_info(identifier),
                    'place_location': await mobile_client.get_place_location(identifier)
                }
            except Exception as e:
                raw_data['mobile_api_error'] = str(e)
        
        # Get data from legacy API
        if api_type in ['legacy', 'auto'] and settings.EGR_API_URL:
            try:
                legacy_client = EGRClient(settings.EGR_API_URL)
                raw_data['legacy_api'] = await legacy_client.get_full_company_history(int(identifier))
            except Exception as e:
                raw_data['legacy_api_error'] = str(e)
        
        return {
            "identifier": identifier,
            "api_type": api_type,
            "data": raw_data
        }
        
    except Exception as e:
        logger.error(f"Error getting raw data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{identifier}/compare")
async def compare_apis(
    identifier: str = Path(..., regex=r'^\d{9}$')
):
    """Сравнить данные из разных API ЕГР"""
    try:
        mobile_data = {}
        legacy_data = {}
        
        if settings.EGR_MOBILE_API_URL:
            mobile_client = MobileEGRClient(settings.EGR_MOBILE_API_URL)
            mobile_data = {
                'common_info': await mobile_client.get_common_info(identifier),
                'place_location': await mobile_client.get_place_location(identifier)
            }
        
        if settings.EGR_API_URL:
            legacy_client = EGRClient(settings.EGR_API_URL)
            legacy_data = await legacy_client.get_full_company_history(int(identifier))
        
        # Compare
        comparison = {
            'identifier': identifier,
            'mobile_api_available': bool(mobile_data.get('common_info')),
            'legacy_api_available': bool(legacy_data),
            'differences': []
        }
        
        # Analyze differences
        if mobile_data.get('common_info') and legacy_data:
            mobile_info = mobile_data['common_info']
            legacy_info = legacy_data.get('base_info', {})
            
            # Compare names
            mobile_name = mobile_info.get('fullNameRus')
            legacy_name = legacy_info.get('VNAIM') or legacy_info.get('VFIO')
            
            if mobile_name != legacy_name:
                comparison['differences'].append({
                    'field': 'name',
                    'mobile': mobile_name,
                    'legacy': legacy_name
                })
        
        return comparison
        
    except Exception as e:
        logger.error(f"Error comparing APIs: {e}")
        raise HTTPException(status_code=500, detail=str(e))






