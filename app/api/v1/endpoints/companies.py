"""Company endpoints"""
from fastapi import APIRouter, HTTPException, Query, Path, Depends
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.schemas.company import CompanyProfileResponse, CompanyLookupResponse
from app.crud.company import CompanyCRUD
from app.services.aggregator import AggregatorService
from app.core.config import settings
from app.services.egr_client import EGRClient, MobileEGRClient
from app.core.logger import get_logger
from app.core.database import get_db
from app.core.security import verify_api_key
from app.database.models import RawCompanyData
from app.tasks.sync_tasks import process_pending_raw

logger = get_logger("api.companies")
router = APIRouter()


@router.get("/lookup", response_model=CompanyLookupResponse)
async def lookup_companies(
    q: str = Query(..., min_length=1, description="Поиск по УНП или названию"),
    limit: int = Query(10, ge=1, le=50, description="Максимум результатов"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """
    Автокомплит по УНП или названию компании.
    Оптимизированная версия с разделением на два типа запросов.
    """
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Параметр 'q' не может быть пустым")

    is_digit = query.isdigit()
    results = []

    if is_digit:
        # Поиск по УНП - быстрый запрос только по индексу
        unp_prefix = f"{query}%"
        sql = text("""
            WITH found_companies AS (
                SELECT c.id, c.unp
                FROM egr_companies c
                WHERE c.unp::text LIKE :unp_prefix
                ORDER BY c.unp
                LIMIT :limit
            )
            SELECT 
                fc.unp,
                n.full_name_ru,
                n.short_name_ru,
                n.full_name_by
            FROM found_companies fc
            LEFT JOIN LATERAL (
                SELECT full_name_ru, short_name_ru, full_name_by
                FROM egr_company_names_history
                WHERE company_id = fc.id
                ORDER BY (valid_to IS NULL) DESC, valid_to DESC NULLS LAST
                LIMIT 1
            ) n ON true
            ORDER BY fc.unp
        """)
        
        rows = db.execute(sql, {
            "unp_prefix": unp_prefix,
            "limit": limit,
        }).mappings().all()
        
    else:
        # Поиск по названию - используем индексы на названиях
        name_term = f"{query}%"
        sql = text("""
            WITH ranked_names AS (
                SELECT DISTINCT ON (n.company_id)
                    c.unp,
                    n.full_name_ru,
                    n.short_name_ru,
                    n.full_name_by
                FROM egr_company_names_history n
                INNER JOIN egr_companies c ON c.id = n.company_id
                WHERE 
                    n.full_name_ru ILIKE :name_term
                    OR n.short_name_ru ILIKE :name_term
                    OR n.full_name_by ILIKE :name_term
                ORDER BY 
                    n.company_id,
                    (n.valid_to IS NULL) DESC,
                    n.valid_to DESC NULLS LAST
            )
            SELECT * FROM ranked_names
            ORDER BY unp
            LIMIT :limit
        """)
        
        rows = db.execute(sql, {
            "name_term": name_term,
            "limit": limit,
        }).mappings().all()

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
    use_mobile_api: Optional[bool] = Query(None, description="Использовать мобильный API"),
    db_only: bool = Query(False, description="Вернуть данные только из БД"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """
    Получить профиль компании или ИП по УНП/PAN
    """
    try:
        if db_only:
            company_crud = CompanyCRUD(db)
            cached = company_crud.get_full_dossier(int(identifier))
            if not cached:
                raise HTTPException(
                    status_code=404,
                    detail=f"Компания с идентификатором {identifier} не найдена в БД"
                )
            return CompanyProfileResponse(**cached)

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
    api_type: str = Query("auto", description="Тип API: mobile, legacy, auto"),
    api_key: str = Depends(verify_api_key),
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


@router.get("/{identifier}/raw/status")
async def get_raw_status(
    identifier: str = Path(..., regex=r'^\d{9}$'),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Статус обработки сырых данных из БД"""
    raw_entry = db.query(RawCompanyData).filter(RawCompanyData.unp == int(identifier)).first()
    if not raw_entry:
        raise HTTPException(status_code=404, detail="Сырые данные не найдены в БД")
    return {
        "unp": raw_entry.unp,
        "processed_at": raw_entry.processed_at.isoformat() if raw_entry.processed_at else None,
        "last_error": raw_entry.last_error,
        "updated_at": raw_entry.updated_at.isoformat() if raw_entry.updated_at else None,
    }


@router.post("/{identifier}/parse")
async def parse_raw_data(
    identifier: str = Path(..., regex=r'^\d{9}$'),
    force: bool = Query(False, description="Перепарсить даже если уже обработано"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Запустить парсинг сырых данных из БД в структурные таблицы"""
    raw_entry = db.query(RawCompanyData).filter(RawCompanyData.unp == int(identifier)).first()
    if not raw_entry:
        raise HTTPException(status_code=404, detail="Сырые данные не найдены в БД")
    if raw_entry.processed_at and not force:
        return {
            "unp": raw_entry.unp,
            "status": "already_processed",
            "processed_at": raw_entry.processed_at.isoformat(),
        }

    aggregator = AggregatorService()
    try:
        aggregator.process_raw_data(int(identifier))
    finally:
        aggregator.close()

    return {
        "unp": raw_entry.unp,
        "status": "processed",
    }


@router.post("/raw/parse-pending")
async def parse_pending_raw(
    limit: int = Query(1000, ge=1, le=10000),
    async_run: bool = Query(False, description="Запустить в фоне через Celery"),
    api_key: str = Depends(verify_api_key),
):
    """Запустить парсинг необработанных сырых данных."""
    if async_run:
        task = process_pending_raw.delay(limit)
        return {"status": "queued", "task_id": task.id, "limit": limit}
    processed = process_pending_raw(limit)
    return {"status": "processed", "count": processed, "limit": limit}


@router.get("/{identifier}/compare")
async def compare_apis(
    identifier: str = Path(..., regex=r'^\d{9}$'),
    api_key: str = Depends(verify_api_key),
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






