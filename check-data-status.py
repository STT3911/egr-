#!/usr/bin/env python3
"""
Скрипт для проверки статуса загрузки и обработки данных
"""
from app.core.database import SessionLocal
from app.database.models import RawCompanyData, Company, CompanyNameHistory, CompanyAddressHistory, CompanyVEDHistory
from sqlalchemy import func, and_


def main():
    print("=" * 80)
    print(" " * 25 + "СТАТУС ДАННЫХ ЕГР")
    print("=" * 80)
    print()
    
    db = SessionLocal()
    try:
        # Raw data statistics
        print("📥 СЫРЫЕ ДАННЫЕ (egr_raw_company_data)")
        print("-" * 80)
        
        total_raw = db.query(RawCompanyData).count()
        print(f"   Всего записей: {total_raw:,}")
        
        if total_raw > 0:
            # Need enrichment
            needs_enrich = db.query(RawCompanyData).filter(
                ~RawCompanyData.data.has_key("names")
                | ~RawCompanyData.data.has_key("addresses")
                | ~RawCompanyData.data.has_key("ved")
            ).count()
            enrich_pct = (needs_enrich / total_raw * 100) if total_raw > 0 else 0
            
            print(f"   Требуют обогащения: {needs_enrich:,} ({enrich_pct:.1f}%)")
            
            # Processed
            processed = db.query(RawCompanyData).filter(
                RawCompanyData.processed_at != None
            ).count()
            processed_pct = (processed / total_raw * 100) if total_raw > 0 else 0
            
            print(f"   Обработано: {processed:,} ({processed_pct:.1f}%)")
            
            # With errors
            has_errors = db.query(RawCompanyData).filter(
                RawCompanyData.last_error != None
            ).count()
            errors_pct = (has_errors / total_raw * 100) if total_raw > 0 else 0
            
            print(f"   С ошибками: {has_errors:,} ({errors_pct:.1f}%)")
            
            # Pending
            pending = total_raw - processed
            pending_pct = (pending / total_raw * 100) if total_raw > 0 else 0
            
            print(f"   Ожидают обработки: {pending:,} ({pending_pct:.1f}%)")
        
        print()
        
        # Processed data statistics
        print("🏢 ОБРАБОТАННЫЕ ДАННЫЕ")
        print("-" * 80)
        
        total_companies = db.query(Company).count()
        print(f"   Компаний (egr_companies): {total_companies:,}")
        
        if total_companies > 0:
            # With names
            companies_with_names = db.query(Company).join(
                CompanyNameHistory
            ).filter(
                CompanyNameHistory.full_name_ru != None
            ).distinct().count()
            names_pct = (companies_with_names / total_companies * 100) if total_companies > 0 else 0
            
            print(f"   С названиями: {companies_with_names:,} ({names_pct:.1f}%)")
            
            # Total history records
            total_names = db.query(CompanyNameHistory).count()
            total_addresses = db.query(CompanyAddressHistory).count()
            total_ved = db.query(CompanyVEDHistory).count()
            
            print(f"   История названий: {total_names:,}")
            print(f"   История адресов: {total_addresses:,}")
            print(f"   История ВЭД: {total_ved:,}")
        
        print()
        
        # Status summary
        print("📊 РЕЗЮМЕ")
        print("-" * 80)
        
        if total_raw == 0:
            print("   ⚠️  Нет данных в БД")
            print()
            print("   Запустите загрузку:")
            print("      python load_json_data.py --sync")
        
        elif needs_enrich > 0:
            print(f"   ⚠️  {needs_enrich:,} записей требуют обогащения")
            print()
            print("   Запустите обогащение:")
            print("      python enrich-data.py")
        
        elif pending > 0:
            print(f"   ⏳ {pending:,} записей ожидают обработки")
            print()
            print("   Обработка запущена автоматически через Celery.")
            print("   Проверьте логи:")
            print("      docker-compose logs -f egr-celery-worker")
        
        elif has_errors > 0:
            print(f"   ⚠️  {has_errors:,} записей с ошибками")
            print()
            print("   Проверьте ошибки:")
            print("      docker exec egr_db psql -U postgres -d egr_db -c \"")
            print("        SELECT unp, last_error FROM egr_raw_company_data")
            print("        WHERE last_error IS NOT NULL LIMIT 10;")
            print("      \"")
        
        else:
            print("   ✅ Все данные загружены и обработаны!")
            print()
            print(f"   Компаний в БД: {total_companies:,}")
            print(f"   С названиями: {companies_with_names:,}")
        
        print()
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()
