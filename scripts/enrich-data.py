#!/usr/bin/env python3
"""
Скрипт для обогащения данных через EGR API

После загрузки данных из JSON файлов, этот скрипт обогащает их
полными данными (names, addresses, VED) через API.
"""
import sys
from app.core.logger import get_logger
from app.tasks.sync_tasks import enrich_missing_raw, process_pending_raw
from app.core.database import SessionLocal
from app.database.models import RawCompanyData

logger = get_logger("enrich_data")


def check_status():
    """Проверить статус данных"""
    db = SessionLocal()
    try:
        total = db.query(RawCompanyData).count()
        
        # Записи требующие обогащения
        needs_enrich = db.query(RawCompanyData).filter(
            ~RawCompanyData.data.has_key("names")
            | ~RawCompanyData.data.has_key("addresses")
            | ~RawCompanyData.data.has_key("ved")
        ).count()
        
        # Записи с ошибками
        has_errors = db.query(RawCompanyData).filter(
            RawCompanyData.last_error != None
        ).count()
        
        # Обработанные записи
        processed = db.query(RawCompanyData).filter(
            RawCompanyData.processed_at != None
        ).count()
        
        return {
            "total": total,
            "needs_enrich": needs_enrich,
            "has_errors": has_errors,
            "processed": processed,
            "pending": total - processed
        }
    finally:
        db.close()


def main():
    print("=" * 70)
    print("📥 ОБОГАЩЕНИЕ ДАННЫХ ЧЕРЕЗ EGR API")
    print("=" * 70)
    print()
    
    # Показать текущий статус
    logger.info("📊 Проверяю текущий статус данных...")
    status = check_status()
    
    print(f"   Всего записей: {status['total']}")
    print(f"   Требуют обогащения: {status['needs_enrich']}")
    print(f"   С ошибками: {status['has_errors']}")
    print(f"   Обработано: {status['processed']}")
    print(f"   Ожидают обработки: {status['pending']}")
    print()
    
    if status['needs_enrich'] == 0:
        logger.info("✅ Все записи уже обогащены!")
        print()
        
        if status['pending'] > 0:
            response = input(f"Обработать {status['pending']} записей в структурные таблицы? (yes/no): ")
            if response.lower() == "yes":
                logger.info("⚙️  Запускаю обработку...")
                processed = process_pending_raw(limit=status['pending'])
                logger.info(f"✅ Обработано {processed} записей")
        
        return
    
    # Спросить подтверждение
    print(f"Будет обогащено до {status['needs_enrich']} записей через EGR API.")
    print("ВНИМАНИЕ: Это может занять много времени!")
    print()
    
    limit = input(f"Сколько записей обогатить? (Enter = все {status['needs_enrich']}): ")
    if limit.strip() == "":
        limit = status['needs_enrich']
    else:
        try:
            limit = int(limit)
        except ValueError:
            logger.error("❌ Неверное число")
            sys.exit(1)
    
    print()
    response = input(f"Обогатить {limit} записей? (yes/no): ")
    if response.lower() != "yes":
        print("❌ Отменено")
        sys.exit(0)
    
    print()
    logger.info(f"🚀 Запускаю обогащение {limit} записей...")
    logger.info("   (Это может занять продолжительное время)")
    print()
    
    try:
        # Обогащение
        enriched = enrich_missing_raw(limit=limit)
        logger.info(f"✅ Обогащено {enriched} из {limit} записей")
        print()
        
        # Спросить про обработку
        if enriched > 0:
            response = input(f"Обработать {enriched} записей в структурные таблицы? (yes/no): ")
            if response.lower() == "yes":
                logger.info("⚙️  Запускаю обработку...")
                processed = process_pending_raw(limit=enriched)
                logger.info(f"✅ Обработано {processed} записей")
        
        print()
        print("=" * 70)
        logger.info("🎉 ЗАВЕРШЕНО!")
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
    main()
