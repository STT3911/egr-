#!/usr/bin/env python3
"""
Скрипт для проверки доступных UNP в базе данных.
Показывает, какие UNP есть в raw_company_data и grp_taxpayer_data.
"""
from app.core.database import SessionLocal
from app.database.models import RawCompanyData, GrpTaxpayerData


def main():
    db = SessionLocal()

    try:
        # Get counts
        raw_count = db.query(RawCompanyData).count()
        grp_count = db.query(GrpTaxpayerData).count()

        print("📊 Состояние данных:")
        print(f"   Всего записей в raw_company_data: {raw_count}")
        print(f"   Всего записей в grp_taxpayer_data: {grp_count}")
        print()

        if raw_count == 0:
            print("❌ Нет данных в raw_company_data!")
            print("   Сначала загрузите данные ЕГР:")
            print("   python scripts/fetch-to-json.py")
            print("   python scripts/load_json_data.py --sync")
            return

        # Get some UNPs from raw data
        raw_unps = db.query(RawCompanyData.unp).order_by(RawCompanyData.unp).limit(20).all()
        raw_unps = [row[0] for row in raw_unps]

        # Get UNPs that already have GRP data
        grp_unps = db.query(GrpTaxpayerData.unp).all()
        grp_unps_set = set(row[0] for row in grp_unps)

        print("🔍 UNP из raw_company_data (первые 20):")
        for i, unp in enumerate(raw_unps, 1):
            has_grp = unp in grp_unps_set
            status = "✅ Есть ГРП" if has_grp else "❌ Нет ГРП"
            print("2d")

        # Show some sample UNPs that need GRP data
        missing_grp = [unp for unp in raw_unps[:10] if unp not in grp_unps_set]
        if missing_grp:
            print()
            print("🎯 UNP без ГРП данных (для тестирования):")
            for unp in missing_grp[:5]:
                print(f"   - {unp}")

        print()
        print("💡 Рекомендации:")
        if missing_grp:
            print("   - Загрузите данные: python scripts/fetch-grp-to-json.py")
        else:
            print("   - Все UNP уже имеют ГРП данные!")
        print("   - Если API недоступен: проверьте VPN или доступ из Беларуси")

    finally:
        db.close()


if __name__ == "__main__":
    main()