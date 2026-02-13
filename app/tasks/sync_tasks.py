"""Synchronization tasks"""
import asyncio
import json
import os
from datetime import date, timedelta, datetime

# Порог размера файла (байт): выше — парсим потоково через ijson, чтобы не грузить весь файл в память
_LARGE_JSON_BYTES = 50 * 1024 * 1024  # 50 MB
from sqlalchemy import or_, text
from app.core.config import settings
from app.core.logger import get_logger
from app.tasks.celery_app import celery_app
from app.services.aggregator import AggregatorService
from app.services.mapper_service import CompanyMapper
from app.crud.company import CompanyCRUD
from app.services.egr_client import EGRClient
from app.services.grp_client import GRPClient
from app.database.models import SystemState, RawCompanyData, GrpTaxpayerData
from app.crud.grp import GrpCRUD
from app.core.database import SessionLocal

logger = get_logger("tasks")


def _needs_enrichment(raw_data: dict) -> bool:
    if not isinstance(raw_data, dict):
        return False
    if "base_info" not in raw_data and "common_info" not in raw_data:
        # Flat base_info payloads from JSON dumps should be enriched too.
        if "ngrn" in raw_data or "NGRN" in raw_data or "nsi00211" in raw_data:
            return True
        return False
    # If any of these are missing/empty, fetch full history
    return not raw_data.get("addresses") or not raw_data.get("names") or not raw_data.get("ved")


@celery_app.task(bind=True, max_retries=3, time_limit=60, soft_time_limit=45)
def sync_specific_company(self, unp: int):
    """Process specific company (time limit 60 sec)"""
    async def _sync():
        service = AggregatorService()
        try:
            success = await service.fetch_and_save_raw(unp)
            if success:
                service.process_raw_data(unp)
            logger.info(f"Successfully synced {unp}")
        except Exception as e:
            logger.error(f"Sync error {unp}: {e}")
            raise self.retry(exc=e, countdown=60)
        finally:
            service.close()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_sync())
    finally:
        loop.close()


@celery_app.task
def reprocess_failed_rows():
    """Reprocess failed data"""
    service = AggregatorService()
    try:
        query = service.db.query(RawCompanyData).filter(
            or_(
                RawCompanyData.processed_at == None,
                RawCompanyData.updated_at > RawCompanyData.processed_at
            )
        ).limit(1000)
        
        count = 0
        for item in query.all():
            try:
                service.process_raw_data(item.unp)
                count += 1
            except Exception as e:
                logger.error(f"Error reprocessing {item.unp}: {e}")
        
        logger.info(f"Reprocessed {count} companies")
    finally:
        service.close()


@celery_app.task
def process_pending_raw(limit: int = 1000):
    """Обогащение по API (если нет names/addresses/ved) + парсинг в структурные таблицы."""
    service = AggregatorService()
    client = EGRClient(settings.EGR_API_URL) if settings.EGR_API_URL else None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    batch_size = 100  # Параллельных запросов к EGR API за один батч (увеличено для скорости; при 429 — уменьшить)
    
    try:
        # Если справочники пусты — парсинг упадёт по FK. Заполняем из raw_data один раз.
        try:
            ref_count = service.db.execute(text("SELECT COUNT(*) FROM ref_creation_methods")).scalar()
            if ref_count == 0:
                logger.info("🔄 Справочники пусты — заполняю из egr_raw_company_data...")
                update_reference_tables.run()
        except Exception as e:
            logger.warning(f"Проверка/заполнение справочников: {e}")

        pending = (
            service.db.query(RawCompanyData)
            .filter(
                (RawCompanyData.processed_at == None)
                | (RawCompanyData.updated_at > RawCompanyData.processed_at)
                | (~RawCompanyData.data.has_key("names"))
                | (~RawCompanyData.data.has_key("addresses"))
                | (~RawCompanyData.data.has_key("ved"))
            )
            .order_by(RawCompanyData.updated_at.asc())
            .limit(limit)
            .all()
        )
        
        if not pending:
            logger.info("No pending raw data to process")
            return 0
        
        logger.info(f"📋 Found {len(pending)} pending records to process")
        
        # Separate: need enrichment vs ready to parse
        needs_enrich = [item for item in pending if _needs_enrichment(item.data or {})]
        ready_to_parse = [item for item in pending if not _needs_enrichment(item.data or {})]
        
        logger.info(f"   Need enrichment: {len(needs_enrich)}, Ready to parse: {len(ready_to_parse)}")
        
        if needs_enrich and not client:
            logger.warning("EGR_API_URL is not set — enrichment skipped. Set EGR_API_URL in .env so data can be enriched.")
        
        # Step 1: Enrich in batches (parallel API calls)
        enriched = 0
        if needs_enrich and client:
            for batch_start in range(0, len(needs_enrich), batch_size):
                batch = needs_enrich[batch_start:batch_start + batch_size]
                logger.info(f"   📥 Enriching batch {batch_start//batch_size + 1}: {len(batch)} companies...")
                
                # Parallel API calls
                async def enrich_batch():
                    tasks = [client.get_full_company_history(item.unp) for item in batch]
                    return await asyncio.gather(*tasks, return_exceptions=True)
                
                results = loop.run_until_complete(enrich_batch())
                
                # Update data (single commit per batch)
                for item, result in zip(batch, results):
                    if isinstance(result, Exception):
                        item.last_error = f"enrich_failed:{str(result)[:200]}"
                        continue
                    if not result:
                        item.last_error = "enrich_failed:no_data"
                        continue
                    
                    item.data = result
                    item.updated_at = datetime.now()
                    item.processed_at = None
                    item.last_error = None
                    enriched += 1
                
                try:
                    service.db.commit()
                    logger.info(f"      ✅ Enriched {enriched} companies")
                except Exception as e:
                    service.db.rollback()
                    logger.error(f"Failed to commit enrichment batch: {e}")
        
        # Step 2: Parse into structured tables (sequential for data integrity)
        to_parse = ready_to_parse + [item for item in needs_enrich if item.last_error is None]
        processed = 0
        
        for item in to_parse:
            try:
                service.process_raw_data(item.unp)
                processed += 1
                
                if processed % 100 == 0:
                    logger.info(f"   ⚙️  Parsed {processed}/{len(to_parse)} companies...")
            except Exception as e:
                item.last_error = f"parse_failed:{str(e)[:500]}"
                service.db.commit()
                logger.error(f"Error processing UNP {item.unp}: {e}")
        
        if processed == 0 and to_parse:
            first_err = (to_parse[0].last_error or "none")[:300]
            logger.warning(
                f"⚠️ No rows parsed in this batch. First last_error sample: {first_err!r}. "
                "Check ref_creation_methods/ref_* tables and run update_reference_tables if needed."
            )
        logger.info(f"✅ Processed {processed}/{len(pending)} pending raw rows")
        return processed
        
    finally:
        if client:
            loop.run_until_complete(client.close())
        loop.close()
        service.close()


@celery_app.task
def enrich_missing_raw(limit: int = 200):
    """Enrich raw rows with parallel processing (5x faster)."""
    service = AggregatorService()
    if not settings.EGR_API_URL:
        logger.warning("EGR_API_URL is not configured; enrichment skipped")
        return 0
    
    client = EGRClient(settings.EGR_API_URL)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    enriched = 0
    
    try:
        candidates = (
            service.db.query(RawCompanyData)
            .order_by(RawCompanyData.updated_at.asc())
            .limit(limit * 5)
            .all()
        )
        
        # Filter candidates that need enrichment
        to_enrich = [item for item in candidates if _needs_enrichment(item.data or {})][:limit]
        
        if not to_enrich:
            logger.info("No rows need enrichment")
            return 0
        
        logger.info(f"📥 Enriching {len(to_enrich)} companies in parallel...")
        
        # Parallel enrichment with asyncio
        async def enrich_batch():
            tasks = []
            for item in to_enrich:
                tasks.append(client.get_full_company_history(item.unp))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results
        
        results = loop.run_until_complete(enrich_batch())
        
        # Save results (single commit for batch)
        for item, result in zip(to_enrich, results):
            if isinstance(result, Exception):
                item.last_error = f"enrich_failed:{str(result)[:200]}"
                logger.warning(f"Enrichment failed for UNP {item.unp}: {result}")
                continue
            
            if not result:
                item.last_error = "enrich_failed:no_data"
                logger.warning(f"No data returned for UNP {item.unp}")
                continue
            
            # Update with enriched data
            item.data = result
            item.updated_at = datetime.now()
            item.processed_at = None  # Will be processed in next step
            item.last_error = None
            enriched += 1
        
        # Single commit for entire batch
        try:
            service.db.commit()
            logger.info(f"✅ Enriched {enriched}/{len(to_enrich)} raw rows")
        except Exception as e:
            service.db.rollback()
            logger.error(f"Failed to commit batch: {e}")
            return 0
        
        return enriched
        
    finally:
        loop.run_until_complete(client.close())
        loop.close()
        service.close()


@celery_app.task(bind=True)
def initial_seed_by_history(self):
    """Initial seed from history"""
    start_date = date(1991, 1, 1)
    end_date = date.today()
    current = start_date
    
    while current < end_date:
        period_end = current + timedelta(days=7)  # 1 week step
        if period_end > end_date:
            period_end = end_date
        
        process_period_range.delay(
            current.strftime("%d.%m.%Y"),
            period_end.strftime("%d.%m.%Y")
        )
        current = period_end


@celery_app.task
def process_period_range(start_str, end_str):
    """
    Process period range: fetch companies and events
    
    This task performs a two-step process:
    1. Fetch all companies registered in the period (getBaseInfoByPeriod)
    2. Fetch all events that occurred in the period (getEventByPeriod)
    """
    async def _run():
        client = EGRClient(settings.EGR_API_URL)
        unps = set()
        
        try:
            # Этап 1: Загружаем базовую информацию о компаниях
            logger.info(f"📋 Step 1: Fetching base info for period {start_str} - {end_str}")
            base_items = await client.get_base_info_by_period(start_str, end_str)
            logger.info(f"✅ Found {len(base_items)} companies (base info)")
            
            for item in base_items:
                unp = item.get("ngrn") or item.get("vunp")
                if unp:
                    unps.add(unp)
            
            # Этап 2: Загружаем события за период
            logger.info(f"📋 Step 2: Fetching events for period {start_str} - {end_str}")
            await asyncio.sleep(0.5)  # Rate limiting
            events = await client.get_events_by_period(start_str, end_str)
            logger.info(f"✅ Found {len(events)} events")
            
            for event in events:
                unp = event.get("ngrn") or event.get("vunp")
                if unp:
                    unps.add(unp)
            
            # Итого
            logger.info(f"🎯 Total unique companies to sync: {len(unps)}")
            
            # Ставим задачи на загрузку каждой компании
            for unp in unps:
                sync_specific_company.delay(unp)

            # Автоматически обновить справочники после загрузки данных
            update_reference_tables.delay()

        except Exception as e:
            logger.error(f"❌ Error processing period {start_str} - {end_str}: {e}")
            raise
        finally:
            pass
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()


def get_last_sync_date(db) -> date:
    """Get last sync date from system state"""
    state = db.query(SystemState).filter(SystemState.key == 'egr_last_sync_date').first()
    return datetime.strptime(state.value, "%Y-%m-%d").date() if state else date.today() - timedelta(days=1)


def update_last_sync_date(db, new_date):
    """Update last sync date"""
    state = db.query(SystemState).filter(SystemState.key == 'egr_last_sync_date').first()
    val = new_date.strftime("%Y-%m-%d")
    if state:
        state.value = val
    else:
        db.add(SystemState(key='egr_last_sync_date', value=val))
    db.commit()


@celery_app.task
def sync_daily_changes():
    """Sync daily changes"""
    async def _run():
        db = SessionLocal()
        client = EGRClient(settings.EGR_API_URL)
        try:
            target_date = date.today() - timedelta(days=1)
            current_cursor = get_last_sync_date(db)
            
            if current_cursor >= target_date:
                logger.info(f"Already synced up to {current_cursor}")
                return

            process_date = current_cursor + timedelta(days=1)
            while process_date <= target_date:
                d_str = process_date.strftime("%d.%m.%Y")
                unps = set()
                
                # Rate limit delay
                await asyncio.sleep(0.5)
                base = await client.get_base_info_by_period(d_str, d_str)
                for i in base:
                    unps.add(i.get("ngrn"))
                
                await asyncio.sleep(0.5)
                events = await client.get_events_by_period(d_str, d_str)
                for e in events:
                    unps.add(e.get("ngrn"))
                
                logger.info(f"Found {len(unps)} companies for {d_str}")
                for unp in unps:
                    if unp:
                        sync_specific_company.delay(unp)
                
                update_last_sync_date(db, process_date)
                process_date += timedelta(days=1)
                
        finally:
            db.close()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()


@celery_app.task
def update_reference_tables():
    """
    Обновить справочники после загрузки новых данных
    Запускать после каждого обновления egr_raw_company_data
    """
    from sqlalchemy import create_engine, text
    import os

    logger.info("🔄 Начинаю обновление справочников...")

    try:
        # Получить параметры подключения к БД
        db_url = settings.DATABASE_URL or os.getenv('DATABASE_URL')
        if not db_url:
            logger.error("❌ DATABASE_URL не настроена")
            return False

        # Создать подключение
        engine = create_engine(db_url)

        # SQL скрипт для обновления справочников
        sql_script = """
        -- Наполнение статусов (COALESCE name — в данных может быть пусто)
        INSERT INTO ref_statuses (id, name, system_id)
        SELECT DISTINCT
            ((data::jsonb->'base_info'->'nsi00219'->>'nksost')::int) as id,
            COALESCE(NULLIF(TRIM(data::jsonb->'base_info'->'nsi00219'->>'vnsostk'), ''), 'Статус ' || (data::jsonb->'base_info'->'nsi00219'->>'nksost')) as name,
            ((data::jsonb->'base_info'->'nsi00219'->>'nsi00219')::int) as system_id
        FROM egr_raw_company_data
        WHERE data::jsonb->'base_info'->'nsi00219' IS NOT NULL
            AND data::jsonb->'base_info'->'nsi00219'->>'nksost' IS NOT NULL
        ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, updated_at = NOW();

        -- Наполнение способов создания
        INSERT INTO ref_creation_methods (id, name, system_id)
        SELECT DISTINCT
            ((data::jsonb->'base_info'->'nsi00208'->>'nkscrt')::int) as id,
            COALESCE(NULLIF(TRIM(data::jsonb->'base_info'->'nsi00208'->>'vnscrtp'), ''), 'Способ создания ' || (data::jsonb->'base_info'->'nsi00208'->>'nkscrt')) as name,
            ((data::jsonb->'base_info'->'nsi00208'->>'nsi00208')::int) as system_id
        FROM egr_raw_company_data
        WHERE data::jsonb->'base_info'->'nsi00208' IS NOT NULL
            AND data::jsonb->'base_info'->'nsi00208'->>'nkscrt' IS NOT NULL
        ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, updated_at = NOW();

        -- Наполнение типов объектов
        INSERT INTO ref_entity_types (id, name, system_id)
        SELECT DISTINCT
            ((data::jsonb->'base_info'->'nsi00211'->>'nkvob')::int) as id,
            COALESCE(NULLIF(TRIM(data::jsonb->'base_info'->'nsi00211'->>'vnvobp'), ''), 'Тип объекта ' || (data::jsonb->'base_info'->'nsi00211'->>'nkvob')) as name,
            ((data::jsonb->'base_info'->'nsi00211'->>'nsi00211')::int) as system_id
        FROM egr_raw_company_data
        WHERE data::jsonb->'base_info'->'nsi00211' IS NOT NULL
            AND data::jsonb->'base_info'->'nsi00211'->>'nkvob' IS NOT NULL
        ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, updated_at = NOW();

        -- Наполнение органов: COALESCE во внутреннем и внешнем SELECT — name NOT NULL в таблице
        INSERT INTO ref_authorities (id, name, system_id)
        SELECT DISTINCT id, COALESCE(NULLIF(TRIM(name), ''), 'Орган ' || id), system_id FROM (
            SELECT
                ((data::jsonb->'base_info'->'nsi00212'->>'nkuz')::int) as id,
                COALESCE(NULLIF(TRIM(data::jsonb->'base_info'->'nsi00212'->>'vnuzp'), ''), 'Орган ' || ((data::jsonb->'base_info'->'nsi00212'->>'nkuz')::int)) as name,
                ((data::jsonb->'base_info'->'nsi00212'->>'nsi00212')::int) as system_id
            FROM egr_raw_company_data WHERE data::jsonb->'base_info'->'nsi00212' IS NOT NULL AND data::jsonb->'base_info'->'nsi00212'->>'nkuz' IS NOT NULL
            UNION ALL
            SELECT
                ((data::jsonb->'base_info'->'nsi00212CRT'->>'nkuz')::int) as id,
                COALESCE(NULLIF(TRIM(data::jsonb->'base_info'->'nsi00212CRT'->>'vnuzp'), ''), 'Орган ' || ((data::jsonb->'base_info'->'nsi00212CRT'->>'nkuz')::int)) as name,
                ((data::jsonb->'base_info'->'nsi00212CRT'->>'nsi00212')::int) as system_id
            FROM egr_raw_company_data WHERE data::jsonb->'base_info'->'nsi00212CRT' IS NOT NULL AND data::jsonb->'base_info'->'nsi00212CRT'->>'nkuz' IS NOT NULL
            UNION ALL
            SELECT
                ((data::jsonb->'base_info'->'nsi00212LKV'->>'nkuz')::int) as id,
                COALESCE(NULLIF(TRIM(data::jsonb->'base_info'->'nsi00212LKV'->>'vnuzp'), ''), 'Орган ' || ((data::jsonb->'base_info'->'nsi00212LKV'->>'nkuz')::int)) as name,
                ((data::jsonb->'base_info'->'nsi00212LKV'->>'nsi00212')::int) as system_id
            FROM egr_raw_company_data WHERE data::jsonb->'base_info'->'nsi00212LKV' IS NOT NULL AND data::jsonb->'base_info'->'nsi00212LKV'->>'nkuz' IS NOT NULL
        ) as all_auths WHERE id IS NOT NULL
        ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, updated_at = NOW();

        -- Наполнение способов ликвидации
        INSERT INTO ref_liquidation_methods (id, name, system_id)
        SELECT DISTINCT
            ((data::jsonb->'base_info'->'nsi00228'->>'nkslkv')::int) as id,
            COALESCE(NULLIF(TRIM(data::jsonb->'base_info'->'nsi00228'->>'vnslkvp'), ''), 'Способ ликвидации ' || (data::jsonb->'base_info'->'nsi00228'->>'nkslkv')) as name,
            ((data::jsonb->'base_info'->'nsi00228'->>'nsi00228')::int) as system_id
        FROM egr_raw_company_data
        WHERE data::jsonb->'base_info'->'nsi00228' IS NOT NULL
            AND data::jsonb->'base_info'->'nsi00228'->>'nkslkv' IS NOT NULL
        ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, updated_at = NOW();
        """

        # Выполнить скрипт
        with engine.connect() as conn:
            conn.execute(text(sql_script))
            conn.commit()

        logger.info("✅ Справочники успешно обновлены")

        # Получить статистику
        stats_query = """
        SELECT
            (SELECT COUNT(*) FROM ref_statuses) as statuses,
            (SELECT COUNT(*) FROM ref_creation_methods) as creation_methods,
            (SELECT COUNT(*) FROM ref_entity_types) as entity_types,
            (SELECT COUNT(*) FROM ref_authorities) as authorities,
            (SELECT COUNT(*) FROM ref_liquidation_methods) as liquidation_methods
        """

        result = conn.execute(text(stats_query)).fetchone()
        logger.info(f"📊 Статистика справочников: {dict(result)}")

        return True

    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении справочников: {e}")
        return False
    finally:
        if 'engine' in locals():
            engine.dispose()


# Максимальный размер файла (байт), для которого при ошибке стриминга пробуем загрузить целиком
_FALLBACK_FULL_LOAD_BYTES = 200 * 1024 * 1024  # 200 MB


# Лимит времени задачи (сек): для файлов 1+ ГБ стриминг может занять несколько часов
_LOAD_JSON_TASK_TIME_LIMIT = 8 * 3600   # 8 часов
_LOAD_JSON_SOFT_TIME_LIMIT = _LOAD_JSON_TASK_TIME_LIMIT - 600  # минус 10 мин


@celery_app.task(bind=True, time_limit=_LOAD_JSON_TASK_TIME_LIMIT, soft_time_limit=_LOAD_JSON_SOFT_TIME_LIMIT)
def load_companies_from_json(self, auto_process: bool = True):
    """
    Load companies from JSON files into DB with automatic processing.
    
    Supports two types of JSON files:
    1. Full data (with names, addresses, ved) - processes directly into tables
    2. Base info only - saves to raw_data, needs enrichment later
    
    Args:
        auto_process: If True, automatically process full data into structured tables
    """
    data_dir = os.path.join("data", "egr_json_full")
    if not os.path.isdir(data_dir):
        logger.warning(f"JSON data directory not found: {data_dir}")
        return 0

    db = SessionLocal()
    mapper = CompanyMapper()
    company_crud = CompanyCRUD(db)
    
    loaded_count = 0
    processed_count = 0
    needs_enrich_count = 0
    batch_size = 500
    failed_files = []

    try:
        json_files = [
            os.path.join(data_dir, name)
            for name in os.listdir(data_dir)
            if name.lower().endswith(".json")
        ]

        logger.info(f"📁 Found {len(json_files)} JSON files to process")

        for file_idx, file_path in enumerate(json_files, 1):
            try:
                file_size = os.path.getsize(file_path)
                use_streaming = file_size > _LARGE_JSON_BYTES
                logger.info(
                    f"📂 Processing file {file_idx}/{len(json_files)}: {os.path.basename(file_path)} "
                    f"({file_size / (1024*1024):.1f} MB)" + (" [streaming]" if use_streaming else "")
                )
            except OSError as e:
                logger.error(f"Failed to stat {file_path}: {e}")
                continue

            def _process_batch(batch, existing_raw_ref):
                """Вставить/обновить raw_data и при auto_process разобрать в таблицы."""
                if not batch:
                    return
                batch_unps = [unp_val for unp_val, _ in batch]
                existing_raw = {
                    r.unp: r for r in
                    db.query(RawCompanyData).filter(RawCompanyData.unp.in_(batch_unps)).all()
                }
                for unp_val, data_val in batch:
                    if unp_val in existing_raw:
                        existing_entry = existing_raw[unp_val]
                        if not _needs_enrichment(data_val) or _needs_enrichment(existing_entry.data or {}):
                            # Проверяем, изменились ли данные перед сбросом processed_at
                            # Сравниваем JSON-представления данных (нормализованные через json.dumps)
                            old_data_json = json.dumps(existing_entry.data, sort_keys=True) if existing_entry.data else None
                            new_data_json = json.dumps(data_val, sort_keys=True) if data_val else None
                            data_changed = old_data_json != new_data_json
                            
                            # Если данные не изменились и запись уже обработана, не сбрасываем processed_at
                            if data_changed or existing_entry.processed_at is None:
                                existing_entry.data = data_val
                                existing_entry.updated_at = datetime.now()
                                existing_entry.processed_at = None
                                existing_entry.last_error = None
                            else:
                                # Данные не изменились, но обновим updated_at для отслеживания последнего обращения
                                existing_entry.updated_at = datetime.now()
                    else:
                        raw_entry = RawCompanyData(unp=unp_val, data=data_val, processed_at=None)
                        db.add(raw_entry)
                        existing_raw[unp_val] = raw_entry
                        nonlocal loaded_count
                        loaded_count += 1
                db.commit()
                if auto_process:
                    for unp_val, data_val in batch:
                        if not _needs_enrichment(data_val):
                            try:
                                db_structure = mapper.map_to_db_structure(int(unp_val), data_val)
                                company_crud.save_full_company_data(db_structure)
                                if unp_val in existing_raw:
                                    existing_raw[unp_val].processed_at = datetime.now()
                                    existing_raw[unp_val].last_error = None
                                nonlocal processed_count
                                processed_count += 1
                            except Exception as e:
                                if unp_val in existing_raw:
                                    existing_raw[unp_val].last_error = str(e)[:500]
                                logger.error(f"Failed to process UNP {unp_val}: {e}")
                        else:
                            nonlocal needs_enrich_count
                            needs_enrich_count += 1
                    db.commit()
                logger.info(f"   ✅ Batch: {len(batch)} saved, {processed_count} processed total")

            batch = []
            try:
                if use_streaming:
                    try:
                        import ijson
                    except ImportError:
                        logger.warning("ijson not installed, falling back to full load (may OOM on huge files)")
                        use_streaming = False
                if use_streaming:
                    stream_ok = False
                    last_stream_err = None
                    for ijson_path in ("item", "data.item", "items.item"):
                        try:
                            with open(file_path, "rb") as fh:
                                for item in ijson.items(fh, ijson_path):
                                    if not isinstance(item, dict):
                                        continue
                                    unp = item.get("ngrn") or item.get("vunp")
                                    if not unp:
                                        continue
                                    raw_data = item if any(k in item for k in ["base_info", "names", "addresses", "ved"]) else {"base_info": item}
                                    batch.append((unp, raw_data))
                                    if len(batch) >= batch_size:
                                        _process_batch(batch, None)
                                        batch = []
                            if batch:
                                _process_batch(batch, None)
                            stream_ok = True
                            break
                        except Exception as stream_err:
                            batch = []
                            db.rollback()
                            last_stream_err = stream_err
                            logger.warning(f"Streaming path '{ijson_path}' failed for {os.path.basename(file_path)}: {stream_err}")
                            continue
                    if not stream_ok:
                        if file_size < _FALLBACK_FULL_LOAD_BYTES:
                            logger.info(f"   Fallback: loading full file ({file_size / (1024*1024):.1f} MB)...")
                            try:
                                with open(file_path, "r", encoding="utf-8") as handle:
                                    payload = json.load(handle)
                                if isinstance(payload, dict):
                                    payload = payload.get("data") or payload.get("items") or payload.get("companies") or []
                                if isinstance(payload, list):
                                    for item in payload:
                                        if not isinstance(item, dict):
                                            continue
                                        unp = item.get("ngrn") or item.get("vunp")
                                        if not unp:
                                            continue
                                        raw_data = item if any(k in item for k in ["base_info", "names", "addresses", "ved"]) else {"base_info": item}
                                        batch.append((unp, raw_data))
                                        if len(batch) >= batch_size:
                                            _process_batch(batch, None)
                                            batch = []
                                    if batch:
                                        _process_batch(batch, None)
                                    logger.info(f"   ✅ Fallback complete for {os.path.basename(file_path)}")
                                else:
                                    failed_files.append((os.path.basename(file_path), "Unsupported JSON structure"))
                            except Exception as fallback_err:
                                logger.error(f"Fallback load failed for {file_path}: {fallback_err}")
                                failed_files.append((os.path.basename(file_path), str(fallback_err)[:200]))
                        else:
                            err_msg = str(last_stream_err or "streaming failed")[:200]
                            logger.error(f"Streaming failed for large file {os.path.basename(file_path)} ({file_size / (1024*1024):.1f} MB): {last_stream_err}")
                            failed_files.append((os.path.basename(file_path), err_msg))
                else:
                    with open(file_path, "r", encoding="utf-8") as handle:
                        payload = json.load(handle)
                    if isinstance(payload, dict):
                        payload = payload.get("data") or payload.get("items") or payload.get("companies") or []
                    if not isinstance(payload, list):
                        logger.warning(f"Unexpected JSON format in {file_path}")
                        continue
                    logger.info(f"   📊 Found {len(payload)} companies in file")
                    for item in payload:
                        if not isinstance(item, dict):
                            continue
                        unp = item.get("ngrn") or item.get("vunp")
                        if not unp:
                            continue
                        raw_data = item if any(k in item for k in ["base_info", "names", "addresses", "ved"]) else {"base_info": item}
                        batch.append((unp, raw_data))
                        if len(batch) >= batch_size:
                            _process_batch(batch, None)
                            batch = []
                    if batch:
                        _process_batch(batch, None)
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to read/process {file_path}: {e}")
                if use_streaming and file_size < _FALLBACK_FULL_LOAD_BYTES:
                    try:
                        with open(file_path, "r", encoding="utf-8") as handle:
                            payload = json.load(handle)
                        if isinstance(payload, dict):
                            payload = payload.get("data") or payload.get("items") or payload.get("companies") or []
                        if isinstance(payload, list):
                            batch = []
                            for item in payload:
                                if not isinstance(item, dict):
                                    continue
                                unp = item.get("ngrn") or item.get("vunp")
                                if not unp:
                                    continue
                                raw_data = item if any(k in item for k in ["base_info", "names", "addresses", "ved"]) else {"base_info": item}
                                batch.append((unp, raw_data))
                                if len(batch) >= batch_size:
                                    _process_batch(batch, None)
                                    batch = []
                            if batch:
                                _process_batch(batch, None)
                            logger.info(f"   ✅ Recovered via full load: {os.path.basename(file_path)}")
                        else:
                            failed_files.append((os.path.basename(file_path), str(e)[:200]))
                    except Exception as e2:
                        failed_files.append((os.path.basename(file_path), str(e2)[:200]))
                else:
                    failed_files.append((os.path.basename(file_path), str(e)[:200]))
                continue

        logger.info(f"")
        logger.info(f"🎉 COMPLETE!")
        logger.info(f"   Loaded: {loaded_count} new records")
        logger.info(f"   Processed: {processed_count} companies")
        logger.info(f"   Need enrichment: {needs_enrich_count}")
        if failed_files:
            logger.warning(f"   ❌ Failed files ({len(failed_files)}):")
            for name, err in failed_files:
                logger.warning(f"      - {name}: {err}")
        
        if needs_enrich_count > 0:
            logger.info(f"")
            logger.info(f"📌 {needs_enrich_count} records need enrichment:")
            logger.info(f"   Run: python enrich-data.py")
        
        return processed_count

    finally:
        db.close()


@celery_app.task
def fetch_period_to_json(start_date: str, end_date: str, output_dir: str = "data/egr_json_full"):
    """
    Fetch companies for period from API and save to JSON with FULL data.
    
    This task:
    1. Gets list of UNPs from getBaseInfoByPeriod
    2. Fetches full company history for each UNP (names, addresses, ved)
    3. Saves to JSON file with complete data
    4. JSON can then be quickly loaded without API calls
    
    Args:
        start_date: Start date in DD.MM.YYYY format
        end_date: End date in DD.MM.YYYY format
        output_dir: Directory to save JSON files
    
    Returns:
        Number of companies saved to JSON
    """
    async def _fetch():
        client = EGRClient(settings.EGR_API_URL)
        companies_data = []
        
        try:
            # Step 1: Get list of companies for period
            logger.info(f"📥 Fetching companies for period {start_date} - {end_date}")
            base_items = await client.get_base_info_by_period(start_date, end_date)
            logger.info(f"✅ Found {len(base_items)} companies")
            
            # Get unique UNPs
            unps = set()
            for item in base_items:
                unp = item.get("ngrn") or item.get("vunp")
                if unp:
                    unps.add(unp)
            
            logger.info(f"📋 Total unique UNPs: {len(unps)}")
            
            # Step 2: Fetch full data for each company
            logger.info(f"📥 Fetching full data for {len(unps)} companies...")
            
            batch_size = 100
            unp_list = list(unps)
            
            for batch_start in range(0, len(unp_list), batch_size):
                batch = unp_list[batch_start:batch_start + batch_size]
                batch_num = batch_start // batch_size + 1
                total_batches = (len(unp_list) + batch_size - 1) // batch_size
                
                logger.info(f"   Batch {batch_num}/{total_batches}: {len(batch)} companies...")
                
                # Parallel fetch
                tasks = [client.get_full_company_history(unp) for unp in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for unp, result in zip(batch, results):
                    if isinstance(result, Exception):
                        logger.warning(f"Failed to fetch UNP {unp}: {result}")
                        continue
                    
                    if result:
                        companies_data.append({
                            "unp": unp,
                            "base_info": result.get("base_info", {}),
                            "names": result.get("names", []),
                            "addresses": result.get("addresses", []),
                            "ved": result.get("ved", [])
                        })
                
                # Rate limiting
                if batch_start + batch_size < len(unp_list):
                    await asyncio.sleep(1)
            
            logger.info(f"✅ Fetched full data for {len(companies_data)} companies")
            
            # Step 3: Save to JSON file
            os.makedirs(output_dir, exist_ok=True)
            filename = f"{start_date.replace('.', '-')}_to_{end_date.replace('.', '-')}.json"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(companies_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ Saved to {filepath}")
            logger.info(f"   File size: {os.path.getsize(filepath) / 1024 / 1024:.2f} MB")
            
            return len(companies_data)
            
        except Exception as e:
            logger.error(f"❌ Error fetching period: {e}")
            raise
        finally:
            await client.close()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_fetch())
    finally:
        loop.close()


@celery_app.task
def auto_fetch_and_load(start_date: str, end_date: str):
    """
    Automatic: Fetch from API to JSON, then load JSON to DB.
    
    This is a high-level task that combines:
    1. fetch_period_to_json() - download full data to JSON
    2. load_companies_from_json() - process JSON into DB
    
    Use this for automatic periodic updates.
    """
    logger.info(f"🚀 AUTO FETCH AND LOAD: {start_date} - {end_date}")
    
    # Step 1: Fetch to JSON
    logger.info(f"📥 Step 1/2: Fetching from API to JSON...")
    count = fetch_period_to_json(start_date, end_date)
    logger.info(f"✅ Fetched {count} companies to JSON")
    
    # Step 2: Load from JSON
    logger.info(f"📂 Step 2/2: Loading from JSON to DB...")
    processed = load_companies_from_json(auto_process=True)
    logger.info(f"✅ Processed {processed} companies")
    
    logger.info(f"🎉 AUTO FETCH AND LOAD COMPLETE!")
    return processed


@celery_app.task
def auto_fetch_recent_to_json_and_db(days_back: int = 3):
    """
    Automatically fetch recent data (last N days) from API to JSON, then load to DB.
    
    This task runs periodically to keep data up-to-date:
    1. Calculates date range (today - N days to today)
    2. Fetches full company data from API
    3. Saves to JSON file
    4. Immediately processes into DB
    
    Args:
        days_back: Number of days to fetch (default: 3)
    """
    from datetime import date, timedelta
    
    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)
    
    start_str = start_date.strftime("%d.%m.%Y")
    end_str = end_date.strftime("%d.%m.%Y")
    
    logger.info(f"")
    logger.info(f"╔═══════════════════════════════════════════════════════════╗")
    logger.info(f"║  AUTO UPDATE: Fetching last {days_back} days ({start_str} - {end_str})  ║")
    logger.info(f"╚═══════════════════════════════════════════════════════════╝")
    logger.info(f"")
    
    try:
        # Fetch and load
        result = auto_fetch_and_load(start_str, end_str)
        
        logger.info(f"")
        logger.info(f"✅ AUTO UPDATE COMPLETE: {result} companies processed")
        logger.info(f"")
        
        return result
    except Exception as e:
        logger.error(f"❌ AUTO UPDATE FAILED: {e}")
        import traceback
        traceback.print_exc()
        raise


@celery_app.task
def auto_fetch_historical_data(start_year: int = 1900, period_months: int = 12):
    """
    Automatically fetch ALL historical data from start_year to today.
    
    Loads data in periods (default: 1 year at a time) to avoid overwhelming the system.
    
    Args:
        start_year: Year to start from (default: 1900)
        period_months: Number of months per period (default: 12 = 1 year)
    
    Returns:
        Total number of companies processed
    """
    from datetime import date, timedelta
    from dateutil.relativedelta import relativedelta
    
    logger.info("")
    logger.info("╔═════════════════════════════════════════════════════════════╗")
    logger.info(f"║  HISTORICAL LOAD: {start_year} → {date.today().year}                    ║")
    logger.info("╚═════════════════════════════════════════════════════════════╝")
    logger.info("")
    
    start_date = date(start_year, 1, 1)
    end_date = date.today()
    
    current_date = start_date
    total_processed = 0
    period_count = 0
    
    try:
        while current_date < end_date:
            # Calculate period end
            period_end = current_date + relativedelta(months=period_months)
            if period_end > end_date:
                period_end = end_date
            
            period_count += 1
            start_str = current_date.strftime("%d.%m.%Y")
            end_str = period_end.strftime("%d.%m.%Y")
            
            logger.info(f"")
            logger.info(f"📅 Period {period_count}: {start_str} - {end_str}")
            logger.info(f"")
            
            try:
                # Fetch and load this period
                result = auto_fetch_and_load(start_str, end_str)
                total_processed += result
                
                logger.info(f"✅ Period {period_count} complete: {result} companies")
                
            except Exception as e:
                logger.error(f"❌ Period {period_count} failed: {e}")
                # Continue with next period even if this one failed
            
            # Move to next period
            current_date = period_end + timedelta(days=1)
        
        logger.info("")
        logger.info("╔═════════════════════════════════════════════════════════════╗")
        logger.info(f"║  HISTORICAL LOAD COMPLETE                                   ║")
        logger.info(f"║  Total: {total_processed} companies processed                      ║")
        logger.info(f"║  Periods: {period_count}                                           ║")
        logger.info("╚═════════════════════════════════════════════════════════════╝")
        logger.info("")
        
        return total_processed
        
    except Exception as e:
        logger.error(f"❌ HISTORICAL LOAD FAILED: {e}")
        import traceback
        traceback.print_exc()
        raise


@celery_app.task
def initial_data_load():
    """Initial data load task - runs periodically for testing"""
    logger.info("🚀 Starting initial data load task")

    service = AggregatorService()
    try:
        # Обновить справочники сначала
        update_reference_tables()

        # Попробовать загрузить несколько тестовых компаний
        test_unps = [100000000, 200000000, 300000000, 400000000]  # Тестовые УНП

        loaded_count = 0
        for unp in test_unps:
            try:
                logger.info(f"📥 Loading test company UNP: {unp}")
                success = asyncio.run(service.fetch_and_save_raw(unp))
                if success:
                    service.process_raw_data(unp)
                    loaded_count += 1
                    logger.info(f"✅ Successfully loaded company {unp}")
                else:
                    logger.warning(f"⚠️ Could not load company {unp}")
            except Exception as e:
                logger.error(f"❌ Error loading company {unp}: {e}")
                continue

        logger.info(f"🎉 Initial data load completed. Loaded {loaded_count} companies.")
        return loaded_count

    except Exception as e:
        logger.error(f"❌ Error in initial data load: {e}")
        return 0
    finally:
        service.close()


@celery_app.task(bind=True, max_retries=2, time_limit=3600, soft_time_limit=3500)
def sync_grp_for_all(self, limit: int = 5000, only_missing: bool = True, batch_size: int = 50):
    """Fetch GRP (налоговая) data for companies from our DB and store into grp_taxpayer_data.

    This task is intentionally conservative (batch processing) to avoid overload / timeouts.
    """
    from app.database.models import Company, GrpTaxpayerData  # local import to avoid cyclic
    from app.crud.grp import GrpCRUD
    from app.services.grp_client import GRPClient
    from sqlalchemy import and_

    db = SessionLocal()
    try:
        base_query = db.query(Company.unp)
        if only_missing:
            base_query = (
                base_query
                .outerjoin(GrpTaxpayerData, Company.unp == GrpTaxpayerData.unp)
                .filter(GrpTaxpayerData.unp == None)  # noqa: E711
            )

        unps = [row[0] for row in base_query.order_by(Company.unp.asc()).limit(limit).all()]

        if not unps:
            logger.info("GRP sync: nothing to do")
            return {"processed": 0, "errors": 0, "limit": limit, "only_missing": only_missing}

        logger.info(f"GRP sync: starting for {len(unps)} companies (only_missing={only_missing})")

        async def _fetch_batch(batch_unps):
            client = GRPClient()
            sem = asyncio.Semaphore(3)  # Conservative concurrency to avoid rate limits

            async def _one(u: int):
                async with sem:
                    max_retries = 3
                    base_delay = 1.5

                    for retry in range(max_retries):
                        try:
                            payload = await client.get_taxpayer(int(u))
                            # Add delay between successful requests
                            await asyncio.sleep(base_delay)
                            return int(u), payload, 200, None
                        except Exception as e:
                            error_msg = str(e)
                            if "429" in error_msg and retry < max_retries - 1:
                                # Rate limit - exponential backoff
                                delay = base_delay * (2 ** retry)
                                logger.warning(f"Rate limit for UNP {u}, retry {retry+1}/{max_retries} after {delay}s")
                                await asyncio.sleep(delay)
                                continue
                            elif ("Server disconnected" in error_msg or "timeout" in error_msg.lower()) and retry < max_retries - 1:
                                # Connection issues - shorter retry
                                delay = base_delay * (retry + 1)
                                logger.warning(f"Connection issue for UNP {u}, retry {retry+1}/{max_retries} after {delay}s")
                                await asyncio.sleep(delay)
                                continue
                            else:
                                return int(u), None, None, error_msg

                    return int(u), None, None, f"Failed after {max_retries} retries"

            try:
                results = await asyncio.gather(*(_one(u) for u in batch_unps))
                return results
            finally:
                await client.close()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        processed = 0
        errors = 0

        crud = GrpCRUD(db)

        try:
            for i in range(0, len(unps), batch_size):
                batch = unps[i:i + batch_size]
                results = loop.run_until_complete(_fetch_batch(batch))

                for u, payload, status, err in results:
                    if err:
                        errors += 1
                    crud.upsert_from_api(unp=u, payload=payload if isinstance(payload, dict) else None, http_status=status, error=err)
                    processed += 1

                db.commit()
                logger.info(f"GRP sync: processed {processed}/{len(unps)}")

        finally:
            loop.close()

        logger.info(f"GRP sync finished: processed={processed}, errors={errors}")
        return {"processed": processed, "errors": errors, "limit": limit, "only_missing": only_missing}

    except Exception as e:
        logger.error(f"GRP sync failed: {e}")
        raise self.retry(exc=e, countdown=300)
    finally:
        db.close()


@celery_app.task
def fetch_grp_to_json(limit: int = 10000, only_missing: bool = True, output_dir: str = "data/grp_json"):
    """
    Fetch GRP taxpayer data from API and save to JSON.

    This task:
    1. Gets list of UNPs from database (companies that need GRP data)
    2. Fetches taxpayer data for each UNP from GRP API
    3. Saves to JSON file
    4. JSON can then be quickly loaded without API calls

    Args:
        limit: Maximum number of UNPs to process
        only_missing: If True, only fetch UNPs that don't have GRP data yet
        output_dir: Directory to save JSON files

    Returns:
        Number of taxpayers saved to JSON
    """
    async def _fetch():
        client = GRPClient()
        taxpayers_data = []

        try:
            # Step 1: Get list of UNPs to process
            db = SessionLocal()
            try:
                query = db.query(RawCompanyData.unp)
                if only_missing:
                    # Only UNPs that don't have GRP data
                    existing_grp_unps = db.query(GrpTaxpayerData.unp).subquery()
                    query = query.filter(~RawCompanyData.unp.in_(existing_grp_unps))

                unps = [row[0] for row in query.order_by(RawCompanyData.unp.asc()).limit(limit).all()]
                logger.info(f"📋 Found {len(unps)} UNPs to fetch GRP data for")
            finally:
                db.close()

            if not unps:
                logger.info("No UNPs to process")
                return 0

            # Step 2: Fetch GRP data for each UNP (parallel with controlled concurrency)
            logger.info(f"📥 Fetching GRP data for {len(unps)} taxpayers (parallel mode with rate limiting)...")

            successful_fetches = 0
            max_retries = 3
            base_delay = 1.15  # Base delay between requests in seconds
            concurrency_limit = 4  # Allow 4 concurrent requests

            async def fetch_single_unp(unp: int):
                nonlocal successful_fetches

                retry_count = 0
                while retry_count < max_retries:
                    try:
                        result = await client.get_taxpayer(unp)

                        if result and isinstance(result, dict):
                            # Transform to our internal format
                            # GRP API returns keys in lowercase
                            taxpayer_record = {
                                "unp": unp,
                                "full_name": result.get("vnaimp") or result.get("VNAIMP"),
                                "short_name": result.get("vnaimk") or result.get("VNAIMK"),
                                "registration_date": result.get("dreg") or result.get("DREG"),
                                "inspectorate_code": result.get("nmns") or result.get("NMNS"),
                                "inspectorate_name": result.get("vmns") or result.get("VMNS"),
                                "status_code": result.get("ckodsost") or result.get("CKODSOST"),
                                "status_date": result.get("dlikv") or result.get("DLIKV"),
                                "address": result.get("vpadres") or result.get("VPADRES"),
                                "raw": result  # Store full raw response
                            }
                            taxpayers_data.append(taxpayer_record)
                            successful_fetches += 1
                            return f"✅ UNP {unp}"
                        else:
                            logger.warning(f"Empty or invalid data returned for UNP {unp}: {result}")
                            return f"⚠️ UNP {unp} - empty data"
                        break  # Success or empty data, exit retry loop

                    except Exception as e:
                        retry_count += 1
                        error_msg = str(e) or "Unknown error"

                        if "429" in error_msg:
                            # Rate limit hit - exponential backoff
                            delay = base_delay * (2 ** retry_count)
                            logger.warning(f"Rate limit hit for UNP {unp}, retry {retry_count}/{max_retries} after {delay}s: {error_msg}")
                            if retry_count < max_retries:
                                await asyncio.sleep(delay)
                                continue
                        elif "Server disconnected" in error_msg or "timeout" in error_msg.lower():
                            # Connection issues - shorter retry
                            delay = base_delay * retry_count
                            logger.warning(f"Connection issue for UNP {unp}, retry {retry_count}/{max_retries} after {delay}s: {error_msg}")
                            if retry_count < max_retries:
                                await asyncio.sleep(delay)
                                continue
                        elif "404" in error_msg or "Not Found" in error_msg:
                            # UNP not found - don't retry
                            logger.warning(f"UNP {unp} not found in GRP (404): {error_msg}")
                            return f"❌ UNP {unp} - not found"
                        else:
                            # Other errors - don't retry
                            logger.warning(f"Failed to fetch GRP data for UNP {unp}: {error_msg}")
                            return f"❌ UNP {unp} - error: {error_msg[:50]}"
                            break

                return f"❌ UNP {unp} - failed after retries"

            # Process in batches with controlled concurrency
            semaphore = asyncio.Semaphore(concurrency_limit)

            async def fetch_with_semaphore(unp):
                async with semaphore:
                    result = await fetch_single_unp(unp)
                    # Small delay between requests even with concurrency
                    await asyncio.sleep(base_delay)
                    return result

            # Process all UNPs with progress reporting
            tasks = [fetch_with_semaphore(unp) for unp in unps]
            results = []

            # Process in chunks to show progress
            chunk_size = concurrency_limit * 10  # Show progress every 30 requests
            for i in range(0, len(tasks), chunk_size):
                chunk = tasks[i:i + chunk_size]
                chunk_results = await asyncio.gather(*chunk, return_exceptions=True)
                results.extend(chunk_results)

                processed = min(i + chunk_size, len(unps))
                logger.info(f"   Processed {processed}/{len(unps)} taxpayers...")

            # Log final results summary
            success_count = sum(1 for r in results if isinstance(r, str) and r.startswith("✅"))
            error_count = sum(1 for r in results if isinstance(r, str) and r.startswith("❌"))
            warning_count = sum(1 for r in results if isinstance(r, str) and r.startswith("⚠️"))

            logger.info(f"   Results: ✅ {success_count} successful, ⚠️ {warning_count} warnings, ❌ {error_count} errors")

            logger.info(f"✅ Fetched GRP data for {successful_fetches} taxpayers")

            # Step 3: Save to JSON file
            if taxpayers_data:
                os.makedirs(output_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"grp_taxpayers_{timestamp}.json"
                filepath = os.path.join(output_dir, filename)

                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(taxpayers_data, f, ensure_ascii=False, indent=2)

                logger.info(f"✅ Saved to {filepath}")
                logger.info(f"   File size: {os.path.getsize(filepath) / 1024 / 1024:.2f} MB")
            else:
                logger.info("No data to save")
                return 0

            return len(taxpayers_data)

        except Exception as e:
            logger.error(f"❌ Error fetching GRP data: {e}")
            raise
        finally:
            await client.close()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_fetch())
    finally:
        loop.close()


@celery_app.task
def load_grp_from_json(auto_process: bool = True, input_dir: str = "data/grp_json"):
    """
    Load GRP taxpayer data from JSON files into database.

    Args:
        auto_process: If True, automatically process and save to GrpTaxpayerData table
        input_dir: Directory containing JSON files

    Returns:
        Number of taxpayers loaded
    """
    if not os.path.isdir(input_dir):
        logger.warning(f"GRP JSON data directory not found: {input_dir}")
        return 0

    db = SessionLocal()
    crud = GrpCRUD(db)
    loaded_count = 0
    batch_size = 500    
    try:
        json_files = [
            os.path.join(input_dir, name)
            for name in os.listdir(input_dir)
            if name.lower().endswith(".json")
        ]

        logger.info(f"📁 Found {len(json_files)} GRP JSON files to process")

        for file_idx, file_path in enumerate(json_files, 1):
            try:
                logger.info(f"📂 Processing file {file_idx}/{len(json_files)}: {os.path.basename(file_path)}")
                with open(file_path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except Exception as e:
                logger.error(f"Failed to read {file_path}: {e}")
                continue

            if not isinstance(payload, list):
                logger.warning(f"Unexpected JSON format in {file_path}")
                continue

            logger.info(f"   📊 Found {len(payload)} taxpayers in file")

            # Process in batches
            batch = []
            for item in payload:
                unp = item.get("unp")
                if not unp:
                    continue

                batch.append(item)

                # Process batch when full
                if len(batch) >= batch_size:
                    try:
                        # Batch upsert to database
                        for taxpayer_data in batch:
                            unp = taxpayer_data["unp"]
                            crud.upsert_from_api(
                                unp=unp,
                                payload=taxpayer_data.get("raw", {}),
                                http_status=200,
                                error=None
                            )
                            loaded_count += 1

                        db.commit()
                        logger.info(f"   ✅ Batch: {len(batch)} saved")

                    except Exception as e:
                        db.rollback()
                        logger.error(f"Batch processing error: {e}")

                    finally:
                        batch = []

            # Process remaining batch
            if batch:
                try:
                    for taxpayer_data in batch:
                        unp = taxpayer_data["unp"]
                        crud.upsert_from_api(
                            unp=unp,
                            payload=taxpayer_data.get("raw", {}),
                            http_status=200,
                            error=None
                        )
                        loaded_count += 1

                    db.commit()
                    logger.info(f"   ✅ Final batch: {len(batch)} saved")

                except Exception as e:
                    db.rollback()
                    logger.error(f"Final batch processing error: {e}")

        logger.info(f"")
        logger.info(f"🎉 COMPLETE!")
        logger.info(f"   Loaded: {loaded_count} taxpayers")

        return loaded_count

    finally:
        db.close()


@celery_app.task
def auto_fetch_grp_and_load(limit: int = 10000, only_missing: bool = True):
    """
    Automatic: Fetch from GRP API to JSON, then load JSON to DB.

    This is a high-level task that combines:
    1. fetch_grp_to_json() - download taxpayer data to JSON
    2. load_grp_from_json() - process JSON into DB

    Use this for automatic periodic updates.
    """
    logger.info(f"🚀 AUTO FETCH GRP AND LOAD: limit={limit}, only_missing={only_missing}")

    # Step 1: Fetch to JSON
    logger.info(f"📥 Step 1/2: Fetching from GRP API to JSON...")
    count = fetch_grp_to_json(limit=limit, only_missing=only_missing)
    logger.info(f"✅ Fetched {count} taxpayers to JSON")

    # Step 2: Load from JSON
    logger.info(f"📂 Step 2/2: Loading from JSON to DB...")
    processed = load_grp_from_json(auto_process=True)
    logger.info(f"✅ Processed {processed} taxpayers")

    logger.info(f"🎉 AUTO FETCH GRP AND LOAD COMPLETE!")
    return processed
