"""Company endpoints"""
import httpx
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
from app.tasks.sync_tasks import process_pending_raw as process_pending_raw_task
from app.utils.search_normalizer import (
    normalize_company_name as normalize_search_name,
    transliterate_query,
)
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
    seen_unps = set()

    def add_lookup_row(row, *, matched_name=None, matched_historical_name=False):
        unp = int(row["unp"])
        if unp in seen_unps:
            return

        name = row["full_name_ru"] or row["short_name_ru"] or row["full_name_by"]
        if not name:
            return

        results.append({
            "unp": unp,
            "name": name,
            "full_name_ru": row["full_name_ru"],
            "short_name_ru": row["short_name_ru"],
            "full_name_by": row["full_name_by"],
            "matched_name": matched_name,
            "matched_historical_name": matched_historical_name,
        })
        seen_unps.add(unp)
    
    # Чистим УНП от пробелов и дефисов
    cleaned_query = re.sub(r'[\s-]', '', query)

    if is_unp_query(cleaned_query):
        # 🔍 ПОИСК ПО УНП - оптимизированный запрос
        logger.info(f"UNP search: {cleaned_query}")
        if len(cleaned_query) == 9:
            try:
                exact_sql = text("""
                    SELECT
                        c.unp,
                        n.full_name_ru,
                        n.short_name_ru,
                        n.full_name_by,
                        COALESCE(pl.address, a.full_address) AS address,
                        rs.name AS status
                    FROM egr_companies c
                    LEFT JOIN LATERAL (
                        SELECT full_name_ru, short_name_ru, full_name_by
                        FROM egr_company_names_history
                        WHERE company_id = c.id
                        ORDER BY (valid_to IS NULL) DESC, valid_to DESC NULLS LAST, valid_from DESC NULLS LAST
                        LIMIT 1
                    ) n ON true
                    LEFT JOIN LATERAL (
                        SELECT full_address
                        FROM egr_company_addresses_history
                        WHERE company_id = c.id
                        ORDER BY (valid_to IS NULL) DESC, valid_to DESC NULLS LAST, valid_from DESC NULLS LAST
                        LIMIT 1
                    ) a ON true
                    LEFT JOIN egr_company_place_locations pl ON pl.unp = c.unp
                    LEFT JOIN ref_statuses rs ON rs.id = c.current_status_code
                    WHERE c.unp = :unp_exact
                    LIMIT 1
                """)
                rows = db.execute(
                    exact_sql,
                    {"unp_exact": int(cleaned_query)},
                ).mappings().all()
            except Exception as e:
                logger.error(f"Error in exact UNP search: {str(e)}")
                raise HTTPException(status_code=500, detail="РћС€РёР±РєР° РїРѕРёСЃРєР° РїРѕ РЈРќРџ")
        
        if len(cleaned_query) == 9:
            for row in rows:
                add_lookup_row(row)

            elapsed = time.time() - start_time
            return {
                "query": query,
                "count": len(results),
                "execution_time": round(elapsed, 3),
                "results": results,
            }

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
        
        for row in rows:
            add_lookup_row(row)

    else:
        # 🔍 УМНЫЙ ПОИСК ПО НАЗВАНИЮ
        search_normalized = normalize_search_name(query)
        
        # Если после нормализации ничего не осталось, используем оригинальный запрос в нижнем регистре
        if not search_normalized:
            search_normalized = query.lower().strip()
            if len(search_normalized) < 2:
                raise HTTPException(status_code=400, detail="Слишком короткий поисковый запрос")
        
        # Транслит-вариант (лат<->кир) для fallback; если нет — дублируем основной,
        # чтобы доп. условие LIKE было безвредным (ничего нового не находит).
        translit_variant = transliterate_query(query)
        translit_normalized = (
            normalize_search_name(translit_variant) or translit_variant
            if translit_variant else search_normalized
        )

        logger.info(f"Smart name search: '{query}' -> '{search_normalized}'")

        try:
            from app.services.search_index import (
                get_queue_status,
                has_pending_index_work,
                search_companies,
            )

            # Мягкий гейт: ES пропускаем только если очередь индексации сильно отстаёт,
            # а не из-за нескольких pending-записей (иначе поиск всегда падает на медленный
            # Postgres LIKE). MAX_OUTSTANDING=0 -> старое строгое поведение.
            skip_es = False
            if settings.ELASTICSEARCH_REQUIRE_SYNCED:
                max_outstanding = settings.ELASTICSEARCH_SYNC_MAX_OUTSTANDING
                if max_outstanding <= 0:
                    skip_es = has_pending_index_work(db)
                else:
                    status = get_queue_status(db)
                    outstanding = status["outstanding"] if status else 0
                    skip_es = outstanding > max_outstanding

            if skip_es:
                logger.info("Elasticsearch lookup skipped: index queue too far behind")
                es_rows = None
            else:
                es_rows = search_companies(query, limit)
        except Exception as e:
            logger.warning(f"Elasticsearch lookup skipped: {e}")
            es_rows = None

        if es_rows:
            for row in es_rows:
                add_lookup_row(
                    row,
                    matched_name=row.get("matched_name"),
                    matched_historical_name=row.get("matched_historical_name", False),
                )

            elapsed = time.time() - start_time
            return {
                "query": query,
                "count": len(results),
                "execution_time": round(elapsed, 3),
                "results": results,
            }
        
        # Для коротких запросов ищем только по началу слова
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
            WHERE (n.search_name LIKE :normalized_contains
                   OR n.search_name LIKE :translit_contains)
              AND n.valid_to IS NULL
            ORDER BY relevance_rank ASC, name_length ASC
            LIMIT :limit
        """)

        try:
            rows = db.execute(sql, {
                "normalized_exact": search_normalized,
                "normalized_start": f"{search_normalized}%",
                "normalized_contains": f"%{search_normalized}%",
                "translit_contains": f"%{translit_normalized}%",
                "limit": limit,
            }).mappings().all()

            for row in rows:
                add_lookup_row(row)

            remaining_limit = limit - len(results)
            if remaining_limit > 0:
                historical_sql = text("""
                    SELECT
                        c.unp,
                        COALESCE(current_n.full_name_ru, hist_n.full_name_ru) AS full_name_ru,
                        COALESCE(current_n.short_name_ru, hist_n.short_name_ru) AS short_name_ru,
                        COALESCE(current_n.full_name_by, hist_n.full_name_by) AS full_name_by,
                        COALESCE(hist_n.full_name_ru, hist_n.short_name_ru, hist_n.full_name_by) AS matched_name,
                        CASE
                            WHEN hist_n.search_name = :normalized_exact THEN 1
                            WHEN hist_n.search_name LIKE :normalized_start THEN 2
                            ELSE 3
                        END as relevance_rank,
                        LENGTH(COALESCE(hist_n.search_name, hist_n.full_name_ru, '')) as name_length
                    FROM egr_company_names_history hist_n
                    JOIN egr_companies c ON c.id = hist_n.company_id
                    LEFT JOIN egr_company_names_history current_n
                       ON current_n.company_id = c.id
                       AND current_n.valid_to IS NULL
                    WHERE hist_n.valid_to IS NOT NULL
                      AND hist_n.search_name IS NOT NULL
                      AND hist_n.search_name != ''
                      AND (hist_n.search_name LIKE :normalized_contains
                           OR hist_n.search_name LIKE :translit_contains)
                    ORDER BY relevance_rank ASC, name_length ASC, hist_n.valid_to DESC NULLS LAST
                    LIMIT :limit
                """)

                historical_rows = db.execute(
                    historical_sql,
                    {
                        "normalized_exact": search_normalized,
                        "normalized_start": f"{search_normalized}%",
                        "normalized_contains": f"%{search_normalized}%",
                        "translit_contains": f"%{translit_normalized}%",
                        "limit": remaining_limit,
                    },
                ).mappings().all()

                for row in historical_rows:
                    add_lookup_row(
                        row,
                        matched_name=row["matched_name"],
                        matched_historical_name=True,
                    )
             
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
        add_lookup_row(row)

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


@router.get("/search/status")
def company_search_status(
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Return Elasticsearch index status."""
    from app.services.search_index import get_index_status

    return get_index_status(db)


@router.post("/search/reindex")
def reindex_company_search(
    limit: Optional[int] = Query(None, ge=1, description="Maximum rows to index"),
    recreate: bool = Query(False, description="Drop and recreate the index first"),
    async_run: bool = Query(True, description="Run in Celery instead of current request"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Rebuild the Elasticsearch company index from PostgreSQL."""
    if async_run:
        from app.tasks.sync_tasks import reindex_elasticsearch

        task = reindex_elasticsearch.delay(limit, recreate)
        return {
            "status": "queued",
            "task_id": task.id,
            "limit": limit,
            "recreate": recreate,
        }

    from app.services.search_index import reindex_companies

    result = reindex_companies(db, limit=limit, recreate=recreate)
    return {"status": "completed", **result}


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
        unp = int(identifier)
        cache_key = f"company_profile_v5:{unp}"

        if not force_refresh and not db_only:
            aggregator = AggregatorService()
            try:
                if aggregator.redis:
                    cached_raw = aggregator.redis.get(cache_key)
                    if cached_raw:
                        import json
                        logger.info(f"Redis cache hit for company profile {unp}")
                        return CompanyProfileResponse(**json.loads(cached_raw))
            except Exception as e:
                logger.warning(f"Redis read error for {unp}: {e}")
            finally:
                aggregator.close()

        company_crud = CompanyCRUD(db)
        cached = company_crud.get_full_dossier(unp)

        if not cached:
            raise HTTPException(
                status_code=404,
                detail=f"Компания с УНП {identifier} не найдена в базе ЕГР"
            )

        if db_only:
            return CompanyProfileResponse(**cached)
        if not force_refresh:
            aggregator = AggregatorService()
            try:
                if aggregator.redis:
                    import json
                    aggregator.redis.setex(
                        cache_key,
                        3600,
                        json.dumps(cached, default=str)
                    )
                    logger.info(f"Saved company profile {unp} to Redis cache")
            except Exception as e:
                logger.warning(f"Redis save error for {unp}: {e}")
            finally:
                aggregator.close()

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
        db.query(
            NalogDebtRecord.debtor_unp,
            NalogDebtRecord.imns_code,
            NalogDebtRecord.imns_name,
            NalogDebtRecord.debt_date,
            NalogDebtRecord.repayment_date,
            NalogDebtRecord.slice_date,
        )
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


@router.get("/{identifier}/related")
async def get_related_companies(
    identifier: str = Path(..., regex=r'^\d{9}$', description="УНП (9 цифр)"),
    limit: int = Query(50, ge=1, le=200, description="Максимум связанных компаний в каждой категории"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Связанные компании: по общим телефону/email и по тому же адресу (здание).

    Данные берутся из периодически пересобираемых агрегатов (company_contacts,
    company_address_keys), поэтому отражают состояние на момент последней
    пересборки (раз в сутки), не текущий момент день-в-день.
    """
    from app.services.company_relations import find_related_by_address, find_related_by_contact

    company = CompanyCRUD(db).get_by_unp(int(identifier))
    if not company:
        raise HTTPException(status_code=404, detail=f"Компания {identifier} не найдена")

    return {
        "unp": int(identifier),
        "by_contact": find_related_by_contact(db, company.id, limit=limit),
        "by_address": find_related_by_address(db, company.id, limit=limit),
    }


@router.get("/{identifier}/geocode")
async def get_company_geocode(
    identifier: str = Path(..., regex=r'^\d{9}$', description="УНП (9 цифр)"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """
    Ленивый геокодинг места нахождения компании.

    Поведение (как договаривались): первый заход — геокодим адрес через
    OSM/Nominatim и сохраняем lat/lon в egr_company_place_locations; последующие
    заходы отдаются из БД. Координаты берём из OSM (лицензия разрешает хранение),
    Яндекс на карточке только РИСУЕТ точку по этим координатам — это его лицензию
    не нарушает. Сброс координат при смене адреса делает egr_sync_place_locations.
    """
    from datetime import datetime, timedelta
    from app.services.geocoding import geocode_address_yandex

    unp = int(identifier)

    row = db.execute(text(
        "SELECT lat, lon, address, geocoded_at FROM egr_company_place_locations WHERE unp = :unp"
    ), {"unp": unp}).first()

    # 1) Координаты уже посчитаны — отдаём из базы.
    if row and row.lat is not None and row.lon is not None:
        return {"unp": unp, "latitude": row.lat, "longitude": row.lon, "cached": True, "address": row.address}

    # 2) Недавно пытались и не нашли — не дёргаем Nominatim на каждом заходе.
    if row and row.geocoded_at is not None:
        if row.geocoded_at > datetime.now() - timedelta(days=settings.GEOCODE_RETRY_AFTER_DAYS):
            return {"unp": unp, "latitude": None, "longitude": None, "cached": False, "address": row.address}

    # 3) Адрес для геокодинга: место нахождения (Mobile API), иначе текущий адрес ЕГР.
    address = row.address if row else None
    if not address:
        addr_row = db.execute(text("""
            SELECT h.full_address
            FROM egr_company_addresses_history h
            JOIN egr_companies c ON c.id = h.company_id
            WHERE c.unp = :unp AND h.valid_to IS NULL
            ORDER BY h.valid_from DESC NULLS LAST
            LIMIT 1
        """), {"unp": unp}).first()
        address = addr_row.full_address if addr_row else None

    if not address:
        return {"unp": unp, "latitude": None, "longitude": None, "cached": False, "address": None}

    # 4) Лёгкий троттлинг общим Redis-локом: гасим всплески одновременных
    #    cache-miss запросов (дневной лимит Яндекс-геокодера ограничен). Занято —
    #    не геокодим сейчас, при следующем заходе попробуем снова (geocoded_at не трогаем).
    aggregator = AggregatorService()
    try:
        r = getattr(aggregator, "redis", None)
        if r is not None:
            try:
                if not r.set("geocode:yandex:lock", "1", nx=True, px=600):
                    return {"unp": unp, "latitude": None, "longitude": None, "cached": False, "address": address}
            except Exception:
                pass
    finally:
        aggregator.close()

    # 5) Геокодим через Яндекс HTTP-геокодер (точно по РБ) и кэшируем результат.
    coords = None
    try:
        async with httpx.AsyncClient(timeout=settings.YANDEX_GEOCODER_TIMEOUT_SECONDS) as http:
            coords = await geocode_address_yandex(http, address)
    except Exception as e:
        logger.warning(f"geocode failed for {unp}: {e}")

    lat, lon = coords if coords else (None, None)

    # geocoded_at ставим всегда (фиксируем попытку). Адрес меняем только если строки
    # ещё не было — у существующей place_location адрес авторитетный (Mobile API).
    try:
        db.execute(text("""
            INSERT INTO egr_company_place_locations (unp, address, lat, lon, geocoded_at, created_at, updated_at)
            VALUES (:unp, :address, :lat, :lon, now(), now(), now())
            ON CONFLICT (unp) DO UPDATE SET
                lat = EXCLUDED.lat,
                lon = EXCLUDED.lon,
                geocoded_at = now(),
                updated_at = now()
        """), {"unp": unp, "address": address, "lat": lat, "lon": lon})
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"failed to persist geocode for {unp}: {e}")

    return {"unp": unp, "latitude": lat, "longitude": lon, "cached": False, "address": address}


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
        task = process_pending_raw_task.delay(limit)
        return {"status": "queued", "task_id": task.id, "limit": limit}
    processed = process_pending_raw_task(limit)
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
        place_location_lat = place_location.lat if place_location else None
        place_location_lon = place_location.lon if place_location else None

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
            "latitude": place_location_lat,
            "longitude": place_location_lon,
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
