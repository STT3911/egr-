#!/usr/bin/env python3
"""
Скрипт для загрузки данных из API ГРП (налоговой) в JSON файлы.

Этот скрипт:
1. Загружает данные о налогоплательщиках из GRP API для UNP из нашей БД
2. Сохраняет в JSON файл
3. JSON можно потом быстро загрузить в БД без API запросов
"""
import sys
from app.core.logger import get_logger
from app.tasks.sync_tasks import fetch_grp_to_json, auto_fetch_grp_and_load

logger = get_logger("fetch_grp_to_json")


def main():
    print("=" * 80)
    print(" " * 20 + "ЗАГРУЗКА ДАННЫХ ГРП ИЗ API В JSON")
    print("=" * 80)
    print()
    print("Этот скрипт загружает данные о налогоплательщиках из GRP API")
    print("и сохраняет в JSON файлы для быстрой последующей загрузки.")
    print()
    print("⚠️  ВНИМАНИЕ: GRP API имеет ограничения на частоту запросов!")
    print("   Загрузка происходит с пагинацией (по 1000 УНП на страницу)")
    print("   и параллельной обработкой (3 одновременных запроса)")
    print("   с автоматической повторной попыткой при ошибках rate limiting.")
    print()

    # Спросить параметры загрузки
    print("Выберите объем загрузки:")
    print("  1. Маленький (1000 UNP)")
    print("  2. Средний (5000 UNP)")
    print("  3. Большой (10000 UNP)")
    print("  4. Свой лимит (ввести число)")
    print()

    choice = input("Ваш выбор (1-4): ").strip()

    if choice == "1":
        limit = 1000
    elif choice == "2":
        limit = 5000
    elif choice == "3":
        limit = 10000
    elif choice == "4":
        print()
        try:
            limit = int(input("Введите лимит UNP: ").strip())
            if limit <= 0:
                raise ValueError()
        except:
            print("❌ Неверное число")
            sys.exit(1)
    else:
        print("❌ Неверный выбор")
        sys.exit(1)

    print()
    print("Какие UNP загружать?")
    print("  1. Только те, по которым нет данных в БД")
    print("  2. Все UNP из БД (обновить существующие)")
    print()

    mode_choice = input("Ваш выбор (1-2, Enter = 1): ").strip() or "1"
    only_missing = mode_choice == "1"

    print()
    print(f"Лимит: {limit} UNP")
    print(f"Режим: {'только недостающие' if only_missing else 'все UNP'}")
    print()

    # Calculate estimated time (parallel processing: 3 concurrent requests)
    # With 3 concurrent requests and 1 second delay between batches
    estimated_seconds = (limit / 3) * 1.5  # ~1.5 seconds per batch of 3 requests
    estimated_minutes = estimated_seconds / 60
    if estimated_minutes > 60:
        estimated_hours = estimated_minutes / 60
        time_est = f"~{estimated_hours:.1f} часов"
    else:
        time_est = f"~{estimated_minutes:.0f} минут"

    print(f"⚠️  Ориентировочное время загрузки: {time_est} (параллельная загрузка)")
    print("   GRP API ограничивает частоту запросов, поэтому используется контролируемая параллельность.")
    print()

    print("Что делать после загрузки в JSON?")
    print("  1. Только сохранить в JSON (быстро)")
    print("  2. Сохранить в JSON И сразу загрузить в БД (автоматически)")
    print()

    process_mode = input("Ваш выбор (1-2, Enter = 2): ").strip() or "2"

    print()
    mode_desc = "только недостающие" if only_missing else "все"
    response = input(f"Начать загрузку {limit} UNP ({mode_desc})? Это займет {time_est}. (yes/no): ")
    if response.lower() != "yes":
        print("❌ Отменено")
        sys.exit(0)

    print()
    logger.info("🚀 Начинаю загрузку ГРП данных...")
    logger.info(f"   Лимит: {limit} UNP")
    logger.info(f"   Режим: {'только недостающие' if only_missing else 'все'}")
    logger.info("")

    try:
        if process_mode == "1":
            # Только в JSON
            logger.info("📥 Загружаю данные из GRP API в JSON...")
            count = fetch_grp_to_json(limit=limit, only_missing=only_missing, page_size=1000)
            logger.info(f"✅ Загружено {count} налогоплательщиков в JSON")
            print()
            print("=" * 80)
            logger.info(f"🎉 ЗАВЕРШЕНО!")
            logger.info(f"   JSON файл сохранен в: data/grp_json/")
            logger.info(f"")
            logger.info(f"Для загрузки в БД запустите:")
            logger.info(f"   python load_grp_json.py --sync")
            print("=" * 80)
        else:
            # В JSON и сразу в БД
            logger.info("📥 Загружаю данные из GRP API в JSON и обрабатываю в БД...")
            result = auto_fetch_grp_and_load(limit=limit, only_missing=only_missing, page_size=1000)
            print()
            print("=" * 80)
            logger.info(f"🎉 ЗАВЕРШЕНО!")
            logger.info(f"   Обработано: {result} налогоплательщиков")
            logger.info(f"   JSON файл сохранен: data/grp_json/")
            print("=" * 80)

    except Exception as e:
        print()
        print("=" * 80)
        logger.error(f"❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()