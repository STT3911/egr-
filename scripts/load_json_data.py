"""
Скрипт для загрузки данных из JSON файлов в базу данных
Файлы должны находиться в data/egr_json_full/

ВАЖНО: JSON файлы содержат только базовую информацию (base_info).
Для полной загрузки требуется 3 шага:
  1. load_companies_from_json() - загрузка base_info в raw_data
  2. enrich_missing_raw() - обогащение через API (добавление names, addresses, VED)
  3. process_pending_raw() - парсинг в структурные таблицы

Для автоматической загрузки используйте auto-import-data.py
"""
import sys
from app.core.logger import get_logger
from app.tasks.sync_tasks import load_companies_from_json, enrich_missing_raw, process_pending_raw

logger = get_logger("load_json")


def main():
    print("=" * 70)
    print("🚀 ЗАГРУЗКА ДАННЫХ ИЗ JSON ФАЙЛОВ (3 ЭТАПА)")
    print("=" * 70)
    print()
    print("Директория: data/egr_json_full/")
    print()
    print("ВНИМАНИЕ: JSON файлы содержат только базовую информацию.")
    print("Для полной загрузки потребуется:")
    print("  1. Загрузка base_info из JSON")
    print("  2. Обогащение через EGR API (names, addresses, VED)")
    print("  3. Обработка в структурные таблицы")
    print()
    
    response = input("Запустить полную загрузку? (yes/no): ")
    if response.lower() != "yes":
        print("❌ Отменено")
        sys.exit(0)
    
    print()
    logger.info("🚀 Запускаю 3-этапную загрузку через Celery...")
    
    # Step 1: Load from JSON
    task1 = load_companies_from_json.delay()
    logger.info(f"📥 Этап 1/3: Загрузка из JSON - задача {task1.id}")
    
    # Step 2: Enrich from API
    task2 = enrich_missing_raw.delay(limit=10000)
    logger.info(f"📥 Этап 2/3: Обогащение через API - задача {task2.id}")
    
    # Step 3: Process into tables
    task3 = process_pending_raw.delay(limit=10000)
    logger.info(f"⚙️  Этап 3/3: Обработка в таблицы - задача {task3.id}")
    
    logger.info("")
    logger.info("✅ Все задачи поставлены в очередь")
    logger.info("")
    logger.info("💡 Отслеживайте прогресс в логах Celery worker:")
    logger.info("   docker-compose logs -f egr-celery-worker")
    logger.info("")
    logger.info("Или запустите синхронно (медленнее, но видно прогресс):")
    logger.info("   python load_json_data.py --sync")
    print()


def main_sync():
    """Запуск задачи синхронно (без Celery) - для небольших датасетов"""
    print("=" * 70)
    print("🚀 СИНХРОННАЯ ЗАГРУЗКА ДАННЫХ ИЗ JSON (3 ЭТАПА)")
    print("=" * 70)
    print()
    
    logger.info("⚙️  Запускаю полную загрузку синхронно...")
    logger.info("   ВНИМАНИЕ: Это может занять много времени для больших датасетов!")
    print()
    
    try:
        # Step 1: Load from JSON
        logger.info("📥 ЭТАП 1/3: Загрузка base_info из JSON файлов...")
        loaded = load_companies_from_json()
        logger.info(f"✅ Загружено {loaded} записей в raw_data")
        print()
        
        # Step 2: Enrich from API
        logger.info("📥 ЭТАП 2/3: Обогащение данных через EGR API...")
        logger.info("   (Это может занять продолжительное время)")
        enriched = enrich_missing_raw(limit=loaded)
        logger.info(f"✅ Обогащено {enriched} из {loaded} записей")
        print()
        
        # Step 3: Process into tables
        logger.info("⚙️  ЭТАП 3/3: Обработка в структурные таблицы...")
        processed = process_pending_raw(limit=loaded)
        logger.info(f"✅ Обработано {processed} записей")
        print()
        
        print("=" * 70)
        logger.info(f"🎉 ЗАВЕРШЕНО!")
        logger.info(f"   Загружено: {loaded}")
        logger.info(f"   Обогащено: {enriched}")
        logger.info(f"   Обработано: {processed}")
        print("=" * 70)
        
    except Exception as e:
        print()
        print("=" * 70)
        logger.error(f"❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--sync":
        main_sync()
    else:
        main()
