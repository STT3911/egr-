from app.tasks.sync_tasks import load_companies_from_json


def main() -> None:
    loaded = load_companies_from_json()
    print(f"Loaded {loaded} companies from JSON.")


if __name__ == "__main__":
    main()
"""
Скрипт для загрузки данных из JSON файлов в базу данных
Файлы должны находиться в data/egr_json_full/
"""
import sys
from app.core.logger import get_logger
from app.tasks.sync_tasks import load_companies_from_json

logger = get_logger("load_json")


def main():
    print("=" * 60)
    print("🚀 ЗАГРУЗКА ДАННЫХ ИЗ JSON ФАЙЛОВ")
    print("=" * 60)
    print()
    print("Директория: data/egr_json_full/")
    print()
    
    response = input("Запустить загрузку? (yes/no): ")
    if response.lower() != "yes":
        print("❌ Отменено")
        sys.exit(0)
    
    print()
    logger.info("🚀 Запускаю задачу загрузки...")
    
    # Запустить задачу через Celery
    result = load_companies_from_json.delay()
    
    logger.info(f"✅ Задача поставлена в очередь с ID: {result.id}")
    logger.info("")
    logger.info("💡 Отслеживайте прогресс в логах Celery worker:")
    logger.info("   docker-compose logs -f egr-celery-worker")
    logger.info("")
    logger.info("Или запустите задачу синхронно (медленнее, но видно прогресс):")
    logger.info("   python load_json_data.py --sync")
    print()


def main_sync():
    """Запуск задачи синхронно (без Celery)"""
    print("=" * 60)
    print("🚀 СИНХРОННАЯ ЗАГРУЗКА ДАННЫХ ИЗ JSON")
    print("=" * 60)
    print()
    
    logger.info("⚙️  Запускаю задачу синхронно...")
    logger.info("   Это может занять несколько минут...")
    print()
    
    try:
        result = load_companies_from_json()
        print()
        print("=" * 60)
        logger.info(f"✅ ЗАВЕРШЕНО! Загружено {result} компаний")
        print("=" * 60)
    except Exception as e:
        print()
        print("=" * 60)
        logger.error(f"❌ ОШИБКА: {e}")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--sync":
        main_sync()
    else:
        main()
