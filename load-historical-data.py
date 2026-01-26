#!/usr/bin/env python3
"""
Скрипт для загрузки ВСЕХ исторических данных с 1900 года по сегодня.

Загружает данные поэтапно (по годам) чтобы не перегрузить систему:
- Для каждого года: загружает из API → сохраняет в JSON → загружает в БД
- JSON файлы остаются как резервная копия
- Можно прервать и продолжить позже
"""
import sys
from datetime import date
from app.core.logger import get_logger
from app.tasks.sync_tasks import auto_fetch_historical_data

logger = get_logger("load_historical")


def main():
    print("=" * 80)
    print(" " * 20 + "ЗАГРУЗКА ИСТОРИЧЕСКИХ ДАННЫХ")
    print("=" * 80)
    print()
    print("Этот скрипт загрузит ВСЕ данные с 1900 года по сегодняшний день.")
    print()
    print("Процесс:")
    print("  1. Загружает данные поэтапно (по годам)")
    print("  2. Для каждого периода:")
    print("     - Загружает из EGR API")
    print("     - Сохраняет ПОЛНЫЕ данные в JSON")
    print("     - Обрабатывает в БД")
    print()
    print("ВАЖНО:")
    print("  - Это займет МНОГО времени (несколько часов)")
    print("  - Будет создано много JSON файлов в data/egr_json_full/")
    print("  - Можно прервать (Ctrl+C) и запустить снова позже")
    print()
    
    # Спросить период
    print("Настройки загрузки:")
    print()
    
    start_year = input("С какого года начать? (Enter = 1900): ").strip()
    if start_year == "":
        start_year = 1900
    else:
        try:
            start_year = int(start_year)
        except:
            print("❌ Неверный год")
            sys.exit(1)
    
    period_months = input("Загружать по сколько месяцев за раз? (Enter = 60 = 5 лет): ").strip()
    if period_months == "":
        period_months = 60
    else:
        try:
            period_months = int(period_months)
        except:
            print("❌ Неверное число")
            sys.exit(1)
    
    print()
    print(f"Будет загружено:")
    print(f"  Период: {start_year} - {date.today().year}")
    print(f"  По {period_months} месяцев за раз")
    print()
    
    # Подсчитать примерное количество периодов
    years = date.today().year - start_year + 1
    periods = (years * 12) // period_months
    
    print(f"Примерно {periods} периодов для загрузки")
    print(f"При скорости ~5-10 минут на период = {periods * 5}-{periods * 10} минут")
    print()
    
    response = input("Начать загрузку? (yes/no): ")
    if response.lower() != "yes":
        print("❌ Отменено")
        sys.exit(0)
    
    print()
    logger.info("🚀 Начинаю историческую загрузку...")
    logger.info(f"   От: {start_year}")
    logger.info(f"   До: {date.today().year}")
    logger.info(f"   Период: {period_months} месяцев")
    logger.info("")
    
    try:
        total = auto_fetch_historical_data(start_year, period_months)
        
        print()
        print("=" * 80)
        logger.info(f"🎉 ЗАВЕРШЕНО!")
        logger.info(f"   Всего обработано: {total} компаний")
        logger.info(f"   JSON файлы сохранены в: data/egr_json_full/")
        print("=" * 80)
        
    except KeyboardInterrupt:
        print()
        print("=" * 80)
        logger.info("⚠️  Прервано пользователем")
        logger.info("   Можно продолжить позже, запустив скрипт снова")
        logger.info("   Уже загруженные данные сохранены в JSON")
        print("=" * 80)
        sys.exit(0)
        
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
