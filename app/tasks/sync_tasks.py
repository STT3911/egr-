"""Synchronization tasks"""
import asyncio
import json
import os
from datetime import date, timedelta, datetime
from sqlalchemy import or_
from app.core.config import settings
from app.core.logger import get_logger
from app.tasks.celery_app import celery_app
from app.services.aggregator import AggregatorService
from app.services.mapper_service import CompanyMapper
from app.crud.company import CompanyCRUD
from app.services.egr_client import EGRClient
from app.database.models import SystemState, RawCompanyData
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
    """Parse pending or stale raw rows into structured tables."""
    service = AggregatorService()
    client = EGRClient(settings.EGR_API_URL) if settings.EGR_API_URL else None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
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
        processed = 0
        for item in pending:
            try:
                if _needs_enrichment(item.data or {}):
                    if not client:
                        item.last_error = "enrich_failed:missing_api_url"
                        service.db.commit()
                        continue
                    full_data = loop.run_until_complete(
                        client.get_full_company_history(item.unp)
                    )
                    if not full_data:
                        item.last_error = "enrich_failed:no_data"
                        service.db.commit()
                        continue
                    logger.info(
                        "Enriched UNP %s: names=%s addresses=%s ved=%s",
                        item.unp,
                        len(full_data.get("names") or []),
                        len(full_data.get("addresses") or []),
                        len(full_data.get("ved") or []),
                    )
                    item.data = full_data
                    item.updated_at = datetime.now()
                    item.processed_at = None
                    item.last_error = None
                    service.db.commit()
                service.process_raw_data(item.unp)
                processed += 1
            except Exception as e:
                logger.error(f"Error processing pending UNP {item.unp}: {e}")
        logger.info(f"Processed {processed}/{len(pending)} pending raw rows")
        return processed
    finally:
        loop.close()
        service.close()


@celery_app.task
def enrich_missing_raw(limit: int = 200):
    """Enrich raw rows that only contain base_info by fetching full history."""
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
        for item in candidates:
            if enriched >= limit:
                break
            if not _needs_enrichment(item.data or {}):
                continue
            try:
                full_data = loop.run_until_complete(client.get_full_company_history(item.unp))
                if not full_data:
                    item.last_error = "enrich_failed"
                    service.db.commit()
                    continue
                item.data = full_data
                item.updated_at = datetime.now()
                item.processed_at = None
                item.last_error = None
                service.db.commit()
                enriched += 1
            except Exception as e:
                item.last_error = f"enrich_failed:{e}"
                service.db.commit()
        logger.info(f"Enriched {enriched} raw rows")
        return enriched
    finally:
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
        -- Наполнение статусов
        INSERT INTO ref_statuses (id, name, system_id)
        SELECT DISTINCT
            ((data::jsonb->'base_info'->'nsi00219'->>'nksost')::int) as id,
            (data::jsonb->'base_info'->'nsi00219'->>'vnsostk') as name,
            ((data::jsonb->'base_info'->'nsi00219'->>'nsi00219')::int) as system_id
        FROM egr_raw_company_data
        WHERE data::jsonb->'base_info'->'nsi00219' IS NOT NULL
            AND data::jsonb->'base_info'->'nsi00219'->>'nksost' IS NOT NULL
        ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, updated_at = NOW();

        -- Наполнение способов создания
        INSERT INTO ref_creation_methods (id, name, system_id)
        SELECT DISTINCT
            ((data::jsonb->'base_info'->'nsi00208'->>'nkscrt')::int) as id,
            (data::jsonb->'base_info'->'nsi00208'->>'vnscrtp') as name,
            ((data::jsonb->'base_info'->'nsi00208'->>'nsi00208')::int) as system_id
        FROM egr_raw_company_data
        WHERE data::jsonb->'base_info'->'nsi00208' IS NOT NULL
            AND data::jsonb->'base_info'->'nsi00208'->>'nkscrt' IS NOT NULL
        ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, updated_at = NOW();

        -- Наполнение типов объектов
        INSERT INTO ref_entity_types (id, name, system_id)
        SELECT DISTINCT
            ((data::jsonb->'base_info'->'nsi00211'->>'nkvob')::int) as id,
            (data::jsonb->'base_info'->'nsi00211'->>'vnvobp') as name,
            ((data::jsonb->'base_info'->'nsi00211'->>'nsi00211')::int) as system_id
        FROM egr_raw_company_data
        WHERE data::jsonb->'base_info'->'nsi00211' IS NOT NULL
            AND data::jsonb->'base_info'->'nsi00211'->>'nkvob' IS NOT NULL
        ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, updated_at = NOW();

        -- Наполнение органов
        INSERT INTO ref_authorities (id, name, system_id)
        SELECT DISTINCT id, name, system_id FROM (
            SELECT
                ((data::jsonb->'base_info'->'nsi00212'->>'nkuz')::int) as id,
                (data::jsonb->'base_info'->'nsi00212'->>'vnuzp') as name,
                ((data::jsonb->'base_info'->'nsi00212'->>'nsi00212')::int) as system_id
            FROM egr_raw_company_data WHERE data::jsonb->'base_info'->'nsi00212' IS NOT NULL
                AND data::jsonb->'base_info'->'nsi00212'->>'nkuz' IS NOT NULL
            UNION ALL
            SELECT
                ((data::jsonb->'base_info'->'nsi00212CRT'->>'nkuz')::int) as id,
                (data::jsonb->'base_info'->'nsi00212CRT'->>'vnuzp') as name,
                ((data::jsonb->'base_info'->'nsi00212CRT'->>'nsi00212')::int) as system_id
            FROM egr_raw_company_data WHERE data::jsonb->'base_info'->'nsi00212CRT' IS NOT NULL
                AND data::jsonb->'base_info'->'nsi00212CRT'->>'nkuz' IS NOT NULL
            UNION ALL
            SELECT
                ((data::jsonb->'base_info'->'nsi00212LKV'->>'nkuz')::int) as id,
                (data::jsonb->'base_info'->'nsi00212LKV'->>'vnuzp') as name,
                ((data::jsonb->'base_info'->'nsi00212LKV'->>'nsi00212')::int) as system_id
            FROM egr_raw_company_data WHERE data::jsonb->'base_info'->'nsi00212LKV' IS NOT NULL
                AND data::jsonb->'base_info'->'nsi00212LKV'->>'nkuz' IS NOT NULL
        ) as all_auths WHERE id IS NOT NULL
        ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, updated_at = NOW();

        -- Наполнение способов ликвидации
        INSERT INTO ref_liquidation_methods (id, name, system_id)
        SELECT DISTINCT
            ((data::jsonb->'base_info'->'nsi00228'->>'nkslkv')::int) as id,
            (data::jsonb->'base_info'->'nsi00228'->>'vnslkvp') as name,
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


@celery_app.task
def load_companies_from_json():
    """Load raw companies from JSON files if present in data/egr_json_full."""
    data_dir = os.path.join("data", "egr_json_full")
    if not os.path.isdir(data_dir):
        logger.warning(f"JSON data directory not found: {data_dir}")
        return 0

    db = SessionLocal()
    mapper = CompanyMapper()
    company_crud = CompanyCRUD(db)
    loaded_count = 0

    try:
        json_files = [
            os.path.join(data_dir, name)
            for name in os.listdir(data_dir)
            if name.lower().endswith(".json")
        ]

        for file_path in json_files:
            try:
                with open(file_path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except Exception as e:
                logger.error(f"Failed to read {file_path}: {e}")
                continue

            if not isinstance(payload, list):
                logger.warning(f"Unexpected JSON format in {file_path}")
                continue

            for item in payload:
                unp = item.get("ngrn") or item.get("vunp")
                if not unp:
                    continue

                raw_data = {"base_info": item}

                raw_entry = db.query(RawCompanyData).filter(RawCompanyData.unp == unp).first()
                if raw_entry:
                    raw_entry.data = raw_data
                    raw_entry.updated_at = datetime.now()
                    raw_entry.processed_at = None
                else:
                    raw_entry = RawCompanyData(unp=unp, data=raw_data)
                    db.add(raw_entry)

                db.commit()

                try:
                    db_structure = mapper.map_to_db_structure(int(unp), raw_data)
                    company_crud.save_full_company_data(db_structure)
                    raw_entry.processed_at = datetime.now()
                    raw_entry.last_error = None
                    db.commit()
                    loaded_count += 1
                except Exception as e:
                    db.rollback()
                    raw_entry.last_error = str(e)
                    db.commit()
                    logger.error(f"Failed to process UNP {unp}: {e}")

        logger.info(f"Loaded {loaded_count} companies from JSON files")
        return loaded_count

    finally:
        db.close()


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


