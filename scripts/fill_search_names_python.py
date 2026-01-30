"""
Заполнение столбца search_name используя Python функцию нормализации.
Более надежно работает с кириллицей чем PostgreSQL regex.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import SessionLocal
from app.utils.search_normalizer import normalize_company_name
from app.core.logger import get_logger

logger = get_logger("fill_search_names")


def fill_search_names(batch_size: int = 5000):
    """Заполняет search_name используя Python функцию."""
    db = SessionLocal()
    
    try:
        # Подсчет записей без search_name
        total_query = text("""
            SELECT COUNT(*) 
            FROM egr_company_names_history 
            WHERE search_name IS NULL OR search_name = ''
        """)
        total = db.execute(total_query).scalar()
        
        logger.info(f"📊 Найдено {total:,} записей для обработки")
        
        if total == 0:
            logger.info("✅ Все записи уже обработаны!")
            return
        
        processed = 0
        updated = 0
        
        while True:
            # Получаем batch записей
            fetch_query = text("""
                SELECT id, full_name_ru, short_name_ru, full_name_by
                FROM egr_company_names_history
                WHERE search_name IS NULL OR search_name = ''
                LIMIT :limit
            """)
            
            rows = db.execute(fetch_query, {"limit": batch_size}).fetchall()
            
            if not rows:
                break
            
            # Подготавливаем batch UPDATE
            updates = []
            for row in rows:
                # Берем первое не-пустое название
                name = row.full_name_ru or row.short_name_ru or row.full_name_by
                
                if name:
                    normalized = normalize_company_name(name)
                    if normalized:
                        updates.append({
                            'id': str(row.id),
                            'search_name': normalized
                        })
                        updated += 1
                
                processed += 1
            
            # Выполняем batch UPDATE
            if updates:
                # Используем CASE для множественного UPDATE
                case_statements = []
                ids = []
                
                for upd in updates:
                    case_statements.append(f"WHEN id = '{upd['id']}' THEN '{upd['search_name']}'")
                    ids.append(f"'{upd['id']}'")
                
                update_sql = text(f"""
                    UPDATE egr_company_names_history
                    SET search_name = CASE
                        {' '.join(case_statements)}
                    END
                    WHERE id IN ({', '.join(ids)})
                """)
                
                db.execute(update_sql)
                db.commit()
            
            progress = (processed / total) * 100
            logger.info(f"📈 Обработано: {processed:,}/{total:,} ({progress:.1f}%) | Обновлено: {updated:,}")
            
            if processed >= total:
                break
        
        logger.info(f"✅ Завершено! Обработано: {processed:,}, обновлено: {updated:,}")
        
        # Финальная статистика
        stats_query = text("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE search_name IS NOT NULL AND search_name != '') as filled
            FROM egr_company_names_history
        """)
        stats = db.execute(stats_query).fetchone()
        logger.info(f"📊 Итого: {stats.filled:,} из {stats.total:,} ({100.0 * stats.filled / stats.total:.1f}%)")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("🚀 Запуск заполнения search_name через Python...")
    fill_search_names()
