#!/usr/bin/env python3
"""
Скрипт для загрузки данных из API ЕГР в JSON файлы с ПОЛНЫМИ данными.

Этот скрипт:
1. Загружает список компаний за указанный период
2. Для каждой компании получает полные данные (names, addresses, ved)
3. Сохраняет в JSON файл
4. JSON можно потом быстро загрузить в БД без API запросов
"""
import sys
from datetime import date, timedelta
from app.core.logger import get_logger
from app.tasks.sync_tasks import fetch_period_to_json, auto_fetch_and_load

logger = get_logger("fetch_to_json")


def main():
    print("=" * 80)
    print(" " * 20 + "ЗАГРУЗКА ДАННЫХ ИЗ API В JSON")
    print("=" * 80)
    print()
    print("Этот скрипт загружает ПОЛНЫЕ данные из EGR API (с названиями, адресами,")
    print("кодами ВЭД) и сохраняет в JSON файлы для быстрой последующей загрузки.")
    print()
    
    # Спросить период
    print("Выберите период загрузки:")
    print("  1. Последние 7 дней")
    print("  2. Последние 30 дней")
    print("  3. Последние 90 дней")
    print("  4. Свой период (ввести даты)")
    print()
    
    choice = input("Ваш выбор (1-4): ").strip()
    
    if choice == "1":
        days = 7
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
    elif choice == "2":
        days = 30
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
    elif choice == "3":
        days = 90
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
    elif choice == "4":
        print()
        start_str = input("Начальная дата (ДД.ММ.ГГГГ): ").strip()
        end_str = input("Конечная дата (ДД.ММ.ГГГГ): ").strip()
        
        try:
            start_date = date(*reversed([int(x) for x in start_str.split('.')]))
            end_date = date(*reversed([int(x) for x in end_str.split('.')]))
        except:
            print("❌ Неверный формат дат")
            sys.exit(1)
    else:
        print("❌ Неверный выбор")
        sys.exit(1)
    
    start_str = start_date.strftime("%d.%m.%Y")
    end_str = end_date.strftime("%d.%m.%Y")
    
    print()
    print(f"Период: {start_str} - {end_str}")
    print()
    print("Что делать после загрузки в JSON?")
    print("  1. Только сохранить в JSON (быстро)")
    print("  2. Сохранить в JSON И сразу загрузить в БД (автоматически)")
    print()
    
    mode = input("Ваш выбор (1-2, Enter = 2): ").strip() or "2"
    
    print()
    response = input(f"Начать загрузку за период {start_str} - {end_str}? (yes/no): ")
    if response.lower() != "yes":
        print("❌ Отменено")
        sys.exit(0)
    
    print()
    logger.info("🚀 Начинаю загрузку...")
    logger.info(f"   Период: {start_str} - {end_str}")
    logger.info("")
    
    try:
        if mode == "1":
            # Только в JSON
            logger.info("📥 Загружаю данные из API в JSON...")
            count = fetch_period_to_json(start_str, end_str)
            logger.info(f"✅ Загружено {count} компаний в JSON")
            print()
            print("=" * 80)
            logger.info(f"🎉 ЗАВЕРШЕНО!")
            logger.info(f"   JSON файл сохранен в: data/egr_json_full/")
            logger.info(f"")
            logger.info(f"Для загрузки в БД запустите:")
            logger.info(f"   python load_json_data.py --sync")
            print("=" * 80)
        else:
            # В JSON и сразу в БД
            logger.info("📥 Загружаю данные из API в JSON и обрабатываю в БД...")
            result = auto_fetch_and_load(start_str, end_str)
            print()
            print("=" * 80)
            logger.info(f"🎉 ЗАВЕРШЕНО!")
            logger.info(f"   Обработано: {result} компаний")
            logger.info(f"   JSON файл сохранен: data/egr_json_full/")
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
