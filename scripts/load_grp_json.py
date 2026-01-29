"""
Скрипт для загрузки данных о налогоплательщиках из JSON файлов в базу данных.

Файлы должны находиться в data/grp_json/

ВАЖНО: JSON файлы содержат полные данные из GRP API.
Для загрузки требуется 1 шаг:
  load_grp_from_json() - загрузка данных в таблицу grp_taxpayer_data
"""
import sys
from app.core.logger import get_logger
from app.tasks.sync_tasks import load_grp_from_json

logger = get_logger("load_grp")


def main():
    print("=" * 70)
    print("🚀 ЗАГРУЗКА ДАННЫХ ГРП ИЗ JSON ФАЙЛОВ")
    print("=" * 70)
    print()
    print("Директория: data/grp_json/")
    print()
    print("ВНИМАНИЕ: JSON файлы содержат полные данные из GRP API.")
    print("Загрузка будет выполнена в таблицу grp_taxpayer_data.")
    print()

    response = input("Запустить загрузку? (yes/no): ")
    if response.lower() != "yes":
        print("❌ Отменено")
        sys.exit(0)

    print()
    logger.info("🚀 Запускаю загрузку через Celery...")

    # Load from JSON
    task = load_grp_from_json.delay()
    logger.info(f"📥 Загрузка из JSON - задача {task.id}")

    logger.info("")
    logger.info("✅ Задача поставлена в очередь")
    logger.info("")
    logger.info("💡 Отслеживайте прогресс в логах Celery worker:")
    logger.info("   docker-compose logs -f egr-celery-worker")
    logger.info("")
    logger.info("Или запустите синхронно (медленнее, но видно прогресс):")
    logger.info("   python load_grp_json.py --sync")
    print()


def main_sync():
    """Запуск задачи синхронно (без Celery)"""
    print("=" * 70)
    print("🚀 СИНХРОННАЯ ЗАГРУЗКА ДАННЫХ ГРП ИЗ JSON")
    print("=" * 70)
    print()

    logger.info("⚙️  Запускаю загрузку синхронно...")

    try:
        # Load from JSON
        logger.info("📥 Загрузка данных из JSON файлов...")
        loaded = load_grp_from_json()
        logger.info(f"✅ Загружено {loaded} налогоплательщиков")
        print()

        print("=" * 70)
        logger.info(f"🎉 ЗАВЕРШЕНО!")
        logger.info(f"   Загружено: {loaded}")
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