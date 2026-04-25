"""Company endpoints"""
from fastapi import APIRouter, HTTPException, Query, Path, Depends
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, text
from app.schemas.company import CompanyProfileResponse, CompanyLookupResponse
from app.schemas.nalog_debt import CompanyNalogDebtResponse, NalogDebtRecordResponse
from app.crud.company import CompanyCRUD
from app.services.aggregator import AggregatorService
from app.core.config import settings
from app.services.egr_client import EGRClient, MobileEGRClient
from app.core.logger import get_logger
from app.core.database import get_db
from app.core.security import verify_api_key
from app.database.models import NalogDebtRecord, RawCompanyData
from app.tasks.sync_tasks import process_pending_raw
from app.utils.search_normalizer import normalize_company_name
from app.core.public_token import verify_public_token


logger = get_logger("api.companies")
router = APIRouter()


import re
import time
from typing import List
from sqlalchemy.sql import text
from fastapi import HTTPException, Query, Depends
from sqlalchemy.orm import Session


def normalize_company_name(name: str) -> str:
    """
    Нормализация названия компании для поиска.
    Убирает ОПФ, пунктуацию, приводит к нижнему регистру.
    """
    if not name:
        return ""
    
    # Приводим к нижнему регистру
    normalized = name.lower().strip()
    
    # Удаляем ОПФ и юридические формы
    opf_patterns = [
        r'\bооо\b', r'\bзао\b', r'\bоао\b', r'\bпао\b',
        r'\bчуп\b', r'\bип\b', r'\bуп\b', r'\bрнуп\b',
        r'\bгпу\b', r'\bфлип\b', r'\bпк\b', r'\bкфх\b',
        r'\bсзоо\b', r'\bсзоао\b', r'\bдоо\b',
        r'\bобщество с ограниченной ответственностью\b',
        r'\bзакрытое акционерное общество\b',
        r'\bоткрытое акционерное общество\b',
        r'\bчастное унитарное предприятие\b',
        r'\bреспубликанское унитарное предприятие\b',
        r'\bобособленное подразделение\b',
        r'\bфилиал\b', r'\bпредставительство\b',
    ]
    
    for pattern in opf_patterns:
        normalized = re.sub(pattern, '', normalized)
    
    # Удаляем кавычки, скобки и другие спецсимволы
    normalized = re.sub(r'["\'«»„"()\[\]{}]', ' ', normalized)
    
    # Заменяем знаки препинания на пробелы
    normalized = re.sub(r'[^\w\s-]', ' ', normalized)
    
    # Удаляем множественные пробелы
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    # Удаляем стоп-слова (только если осталось достаточно слов)
    stop_words = {'для', 'по', 'и', 'или', 'на', 'с', 'из', 'в', 'о', 'у', 'к'}
    words = normalized.split()
    if len(words) > 2:
        words = [w for w in words if w not in stop_words and len(w) > 1]
    
    normalized = ' '.join(words)
    
    return normalized if normalized and len(normalized) >= 2 else ""


def is_unp_query(query: str) -> bool:
    """Проверяет, является ли запрос поиском по УНП"""
    # Убираем все пробелы и дефисы
    cleaned = re.sub(r'[\s-]', '', query)
    
    # Проверяем, что это только цифры и длина подходит для УНП
    if cleaned.isdigit():
        # УНП Беларуси: 9 цифр, но можем искать по частичному УНП
        return 1 <= len(cleaned) <= 12
    
    return False


@router.get("/lookup", response_model=CompanyLookupResponse)
def lookup_companies(
    q: str = Query(..., min_length=1, description="Поиск по УНП или названию"),
    limit: int = Query(10, ge=1, le=50, description="Максимум результатов"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """
    🔍 Умный поиск по УНП или названию компании.
    
    **Для УНП:** Быстрый поиск по индексу
    **Для названия:** Умный поиск с автоматической нормализацией:
    - Убирает ОПФ (ООО, ЗАО, ИП и т.п.)
    - Игнорирует спецсимволы и регистр
    - Находит при неточном вводе
    
    **Примеры:**
    - `123456` → поиск по УНП
    - `ООО Минск` → найдет компании с "минск" (без учета ОПФ)
    - `Рога и Копыта` → найдет независимо от ОПФ
    """
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Параметр 'q' не может быть пустым")

    start_time = time.time()
    results = []
    
    # Чистим УНП от пробелов и дефисов
    cleaned_query = re.sub(r'[\s-]', '', query)

    if is_unp_query(cleaned_query):
        # 🔍 ПОИСК ПО УНП - оптимизированный запрос
        logger.info(f"UNP search: {cleaned_query}")
        
        sql = text("""
            SELECT DISTINCT ON (c.unp)
                c.unp,
                n.full_name_ru,
                n.short_name_ru,
                n.full_name_by
            FROM egr_companies c
            INNER JOIN egr_company_names_history n ON n.company_id = c.id
            WHERE 
                CAST(c.unp AS TEXT) LIKE :unp_pattern || '%'
                AND n.valid_to IS NULL
            ORDER BY 
                c.unp,
                -- Сначала точное совпадение
                CASE WHEN CAST(c.unp AS TEXT) = :unp_exact THEN 0 ELSE 1 END,
                -- Затем актуальные записи
                (n.valid_to IS NULL) DESC,
                n.valid_to DESC NULLS LAST
            LIMIT :limit
        """)
        
        try:
            rows = db.execute(sql, {
                "unp_pattern": cleaned_query,
                "unp_exact": cleaned_query,
                "limit": limit,
            }).mappings().all()
            
        except Exception as e:
            logger.error(f"Error in UNP search: {str(e)}")
            raise HTTPException(status_code=500, detail="Ошибка поиска по УНП")
        
    else:
        # 🔍 УМНЫЙ ПОИСК ПО НАЗВАНИЮ
        search_normalized = normalize_company_name(query)
        
        # Если после нормализации ничего не осталось, используем оригинальный запрос в нижнем регистре
        if not search_normalized:
            search_normalized = query.lower().strip()
            if len(search_normalized) < 2:
                raise HTTPException(status_code=400, detail="Слишком короткий поисковый запрос")
        
        logger.info(f"Smart name search: '{query}' -> '{search_normalized}'")
        
        # Для коротких запросов ищем только по началу слова
        search_mode = "starts_with" if len(search_normalized) <= 3 else "contains"
        
        sql = text("""
            SELECT
                c.unp,
                n.full_name_ru,
                n.short_name_ru,
                n.full_name_by,
                CASE
                    WHEN n.search_name = :normalized_exact THEN 1
                    WHEN n.search_name LIKE :normalized_start THEN 2
                    ELSE 3
                END as relevance_rank,
                LENGTH(COALESCE(n.search_name, n.full_name_ru, '')) as name_length
            FROM egr_company_names_history n
            JOIN egr_companies c ON c.id = n.company_id
            WHERE n.search_name LIKE :normalized_contains
              AND n.valid_to IS NULL
            ORDER BY relevance_rank ASC, name_length ASC
            LIMIT :limit
        """)
        
        try:
            rows = db.execute(sql, {
                "normalized_exact": search_normalized,
                "normalized_start": f"{search_normalized}%",
                "normalized_contains": f"%{search_normalized}%",
                "limit": limit,
            }).mappings().all()
            
        except Exception as e:
            logger.error(f"Error in name search: {str(e)}")
            # Fallback на простой поиск
            sql_fallback = text("""
                SELECT DISTINCT ON (c.unp)
                    c.unp,
                    n.full_name_ru,
                    n.short_name_ru,
                    n.full_name_by
                FROM egr_companies c
                INNER JOIN egr_company_names_history n ON n.company_id = c.id
                WHERE (n.valid_to IS NULL OR n.valid_to > NOW())
                AND (
                    n.full_name_ru ILIKE :pattern
                    OR n.short_name_ru ILIKE :pattern
                    OR n.full_name_by ILIKE :pattern
                )
                ORDER BY c.unp
                LIMIT :limit
            """)
            
            rows = db.execute(sql_fallback, {
                "pattern": f"%{query}%",
                "limit": limit,
            }).mappings().all()
    
    # Формируем результаты
    for row in rows:
        name = row["full_name_ru"] or row["short_name_ru"] or row["full_name_by"]
        if name:  # Только если есть название
            results.append({
                "unp": int(row["unp"]),
                "name": name,
                "full_name_ru": row["full_name_ru"],
                "short_name_ru": row["short_name_ru"],
                "full_name_by": row["full_name_by"],
            })

    # Логируем производительность
    elapsed = time.time() - start_time
    if elapsed > 1.0:
        logger.warning(f"Slow search ({elapsed:.2f}s): '{query}' returned {len(results)} results")
    
    return {
        "query": query,
        "count": len(results),
        "execution_time": round(elapsed, 3),
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
        company_crud = CompanyCRUD(db)
        cached = company_crud.get_full_dossier(int(identifier))
        if not cached:
            raise HTTPException(
                status_code=404,
                detail=f"Компания с УНП {identifier} не найдена в базе ЕГР"
            )

        if db_only:
            return CompanyProfileResponse(**cached)

        # Check if mobile API is configured
        if use_mobile_api and not settings.EGR_MOBILE_API_URL:
            raise HTTPException(
                status_code=400,
                detail="Мобильный API не настроен"
            )

        if force_refresh:
            aggregator = AggregatorService()
            try:
                profile = await aggregator.get_company_profile(
                    identifier=identifier,
                    use_cache=False
                )
            finally:
                aggregator.close()

            if profile:
                return CompanyProfileResponse(**profile)

        return CompanyProfileResponse(**cached)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting company profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{identifier}/tax-debt", response_model=CompanyNalogDebtResponse)
async def get_company_tax_debt(
    identifier: str = Path(..., regex=r'^\d{9}$', description="УНП (9 цифр)"),
    limit: int = Query(100, ge=1, le=1000, description="Сколько записей задолженности вернуть"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Return tax debt records for a company by UNP."""
    unp = int(identifier)
    rows = (
        db.query(NalogDebtRecord)
        .filter(NalogDebtRecord.debtor_unp == unp)
        .order_by(desc(NalogDebtRecord.slice_date), NalogDebtRecord.debt_date, NalogDebtRecord.imns_code)
        .limit(limit)
        .all()
    )

    latest_slice = rows[0].slice_date.isoformat() if rows and rows[0].slice_date else None
    items = [
        NalogDebtRecordResponse(
            debtor_unp=int(row.debtor_unp),
            imns_code=row.imns_code,
            imns_name=row.imns_name,
            debt_date=row.debt_date,
            repayment_date=row.repayment_date,
            slice_date=row.slice_date.isoformat(),
        )
        for row in rows
    ]

    return CompanyNalogDebtResponse(
        unp=unp,
        count=len(items),
        latest_slice_date=latest_slice,
        items=items,
    )


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


@router.get("/public/{identifier}", response_model=CompanyProfileResponse)
async def get_company_public(
    identifier: str = Path(..., regex=r'^\d{9}$', description="УНП (9 цифр)"),
    db: Session = Depends(get_db),
    token: str = Depends(verify_public_token),
):
    """
    Публичный эндпоинт — текущие данные по компании без истории.
    Требует Bearer токен в заголовке Authorization.
    """
    try:
        company_crud = CompanyCRUD(db)
        from sqlalchemy.orm import joinedload
        from app.database.models import Company, ReferenceStatus

        company = (
            db.query(Company)
            .options(
                joinedload(Company.names_history),
                joinedload(Company.addresses_history),
                joinedload(Company.ved_history),
                joinedload(Company.contacts_history),
            )
            .filter(Company.unp == int(identifier))
            .first()
        )

        if not company:
            raise HTTPException(status_code=404, detail=f"Компания {identifier} не найдена")

        # Текущее название (valid_to IS NULL)
        current_name = next(
            (n for n in sorted(company.names_history, key=lambda n: n.valid_to is None, reverse=True)),
            None
        )

        # Текущий адрес
        current_address = next(
            (a for a in sorted(company.addresses_history, key=lambda a: a.valid_to is None, reverse=True)),
            None
        )

        # Текущие ВЭД (только активные)
        current_ved = [v for v in company.ved_history if v.valid_to is None]

        # Текущие контакты (только активные)
        current_contacts = [c for c in company.contacts_history if c.valid_to is None]

        # Место нахождения из egr_company_place_locations
        from app.database.models import CompanyPlaceLocation
        place_location = db.query(CompanyPlaceLocation).filter(
            CompanyPlaceLocation.unp == int(identifier)
        ).first()
        place_location_address = place_location.address if place_location else None

        # Статус
        status_name = None
        if company.current_status_code:
            status = db.query(ReferenceStatus).filter(
                ReferenceStatus.id == company.current_status_code
            ).first()
            if status:
                status_name = status.name

        return {
            "unp": company.unp,
            "current_status_code": company.current_status_code,
            "current_status_name": status_name,
            "registration_date": company.registration_date.isoformat() if company.registration_date else None,
            "liquidation_date": company.liquidation_date.isoformat() if company.liquidation_date else None,
            "current_name_ru": current_name.full_name_ru if current_name else None,
            "current_short_name_ru": current_name.short_name_ru if current_name else None,
            "current_name_by": current_name.full_name_by if current_name else None,
            "place_location_address": place_location_address,
            "names": [],  # история скрыта
            "addresses": [
                {
                    "full_address": current_address.full_address,
                    "postal_code": current_address.postal_code,
                    "region": current_address.region,
                    "district": current_address.district,
                    "valid_from": current_address.valid_from.isoformat() if current_address.valid_from else None,
                    "valid_to": None,
                }
            ] if current_address else [],
            "ved": [
                {
                    "ved_code": v.ved_code,
                    "ved_name": v.ved_name,
                    "valid_from": v.valid_from.isoformat() if v.valid_from else None,
                    "valid_to": None,
                }
                for v in current_ved
            ],
            "contacts": [
                {
                    "email": c.email,
                    "website": c.website,
                    "phone": c.phone,
                    "fax": c.fax,
                }
                for c in current_contacts
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Public API error for {identifier}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
