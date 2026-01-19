"""
Скрипт для загрузки справочников из JSON файлов
Использование: python load_from_json.py file1.json file2.json
"""
import json
import sys
import os
from pathlib import Path
from typing import Dict, Set, List
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_batch

# Конфигурация БД из переменных окружения
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'dbname': os.getenv('DB_NAME', 'tendex_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', ''),
}


class ReferenceDataExtractor:
    """Извлекает справочные данные из JSON"""
    
    def __init__(self):
        self.statuses: Dict[int, Dict] = {}
        self.creation_methods: Dict[int, Dict] = {}
        self.entity_types: Dict[int, Dict] = {}
        self.authorities: Dict[int, Dict] = {}
        self.liquidation_methods: Dict[int, Dict] = {}
    
    def extract_from_json(self, data: Dict):
        """Извлекает справочные данные из одной JSON записи"""
        base_info = data.get('base_info', {})
        
        # 1. Статус
        if 'nsi00219' in base_info and base_info['nsi00219']:
            nsi = base_info['nsi00219']
            if 'nksost' in nsi and nsi['nksost']:
                self.statuses[nsi['nksost']] = {
                    'id': nsi['nksost'],
                    'name': nsi.get('vnsostk', ''),
                    'system_id': nsi.get('nsi00219')
                }
        
        # 2. Способ создания
        if 'nsi00208' in base_info and base_info['nsi00208']:
            nsi = base_info['nsi00208']
            if 'nkscrt' in nsi and nsi['nkscrt']:
                self.creation_methods[nsi['nkscrt']] = {
                    'id': nsi['nkscrt'],
                    'name': nsi.get('vnscrtp', ''),
                    'system_id': nsi.get('nsi00208')
                }
        
        # 3. Тип объекта (ЮЛ/ИП)
        if 'nsi00211' in base_info and base_info['nsi00211']:
            nsi = base_info['nsi00211']
            if 'nkvob' in nsi and nsi['nkvob']:
                self.entity_types[nsi['nkvob']] = {
                    'id': nsi['nkvob'],
                    'name': nsi.get('vnvobp', ''),
                    'system_id': nsi.get('nsi00211')
                }
        
        # 4. Органы (из трех мест)
        # А. Текущий орган
        if 'nsi00212' in base_info and base_info['nsi00212']:
            nsi = base_info['nsi00212']
            if 'nkuz' in nsi and nsi['nkuz']:
                self.authorities[nsi['nkuz']] = {
                    'id': nsi['nkuz'],
                    'name': nsi.get('vnuzp', ''),
                    'system_id': nsi.get('nsi00212')
                }
        
        # Б. Орган создания
        if 'nsi00212CRT' in base_info and base_info['nsi00212CRT']:
            nsi = base_info['nsi00212CRT']
            if 'nkuz' in nsi and nsi['nkuz']:
                self.authorities[nsi['nkuz']] = {
                    'id': nsi['nkuz'],
                    'name': nsi.get('vnuzp', ''),
                    'system_id': nsi.get('nsi00212')
                }
        
        # В. Орган ликвидации
        if 'nsi00212LKV' in base_info and base_info['nsi00212LKV']:
            nsi = base_info['nsi00212LKV']
            if 'nkuz' in nsi and nsi['nkuz']:
                self.authorities[nsi['nkuz']] = {
                    'id': nsi['nkuz'],
                    'name': nsi.get('vnuzp', ''),
                    'system_id': nsi.get('nsi00212')
                }
        
        # 5. Способ ликвидации
        if 'nsi00228' in base_info and base_info['nsi00228']:
            nsi = base_info['nsi00228']
            if 'nkslkv' in nsi and nsi['nkslkv']:
                self.liquidation_methods[nsi['nkslkv']] = {
                    'id': nsi['nkslkv'],
                    'name': nsi.get('vnslkvp', ''),
                    'system_id': nsi.get('nsi00228')
                }
    
    def get_statistics(self):
        """Возвращает статистику собранных данных"""
        return {
            'statuses': len(self.statuses),
            'creation_methods': len(self.creation_methods),
            'entity_types': len(self.entity_types),
            'authorities': len(self.authorities),
            'liquidation_methods': len(self.liquidation_methods)
        }


def load_json_file(file_path: str) -> List[Dict]:
    """Загружает данные из JSON файла"""
    print(f"📂 Читаю файл: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Если это массив - вернуть как есть
    if isinstance(data, list):
        print(f"   ✅ Загружено {len(data)} записей")
        return data
    
    # Если это один объект - обернуть в массив
    print(f"   ✅ Загружен 1 объект")
    return [data]


def insert_to_database(conn, extractor: ReferenceDataExtractor):
    """Вставляет данные в базу данных"""
    cursor = conn.cursor()
    
    print("\n" + "="*60)
    print("💾 ЗАГРУЗКА В БАЗУ ДАННЫХ")
    print("="*60)
    
    # 1. Статусы
    if extractor.statuses:
        data = [(v['id'], v['name'], v['system_id']) for v in extractor.statuses.values()]
        execute_batch(cursor, """
            INSERT INTO ref_statuses (id, name, system_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE 
            SET name = EXCLUDED.name, updated_at = NOW()
        """, data)
        print(f"✅ ref_statuses: {len(data)} записей")
    
    # 2. Способы создания
    if extractor.creation_methods:
        data = [(v['id'], v['name'], v['system_id']) for v in extractor.creation_methods.values()]
        execute_batch(cursor, """
            INSERT INTO ref_creation_methods (id, name, system_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE 
            SET name = EXCLUDED.name, updated_at = NOW()
        """, data)
        print(f"✅ ref_creation_methods: {len(data)} записей")
    
    # 3. Типы объектов
    if extractor.entity_types:
        data = [(v['id'], v['name'], v['system_id']) for v in extractor.entity_types.values()]
        execute_batch(cursor, """
            INSERT INTO ref_entity_types (id, name, system_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE 
            SET name = EXCLUDED.name, updated_at = NOW()
        """, data)
        print(f"✅ ref_entity_types: {len(data)} записей")
    
    # 4. Органы
    if extractor.authorities:
        data = [(v['id'], v['name'], v['system_id']) for v in extractor.authorities.values()]
        execute_batch(cursor, """
            INSERT INTO ref_authorities (id, name, system_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE 
            SET name = EXCLUDED.name, updated_at = NOW()
        """, data)
        print(f"✅ ref_authorities: {len(data)} записей")
    
    # 5. Способы ликвидации
    if extractor.liquidation_methods:
        data = [(v['id'], v['name'], v['system_id']) for v in extractor.liquidation_methods.values()]
        execute_batch(cursor, """
            INSERT INTO ref_liquidation_methods (id, name, system_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE 
            SET name = EXCLUDED.name, updated_at = NOW()
        """, data)
        print(f"✅ ref_liquidation_methods: {len(data)} записей")
    
    conn.commit()
    cursor.close()


def main():
    if len(sys.argv) < 2:
        print("❌ Использование: python load_from_json.py file1.json file2.json ...")
        sys.exit(1)
    
    json_files = sys.argv[1:]
    
    print("="*60)
    print("🚀 ЗАГРУЗКА СПРАВОЧНИКОВ ИЗ JSON")
    print("="*60)
    print(f"Файлов для обработки: {len(json_files)}")
    print()
    
    # Инициализация экстрактора
    extractor = ReferenceDataExtractor()
    
    # Обработка всех JSON файлов
    total_records = 0
    for json_file in json_files:
        if not os.path.exists(json_file):
            print(f"⚠️  Файл не найден: {json_file}")
            continue
        
        try:
            records = load_json_file(json_file)
            for record in records:
                extractor.extract_from_json(record)
                total_records += 1
        except Exception as e:
            print(f"❌ Ошибка при обработке {json_file}: {e}")
            continue
    
    # Статистика
    stats = extractor.get_statistics()
    print("\n" + "="*60)
    print("📊 СТАТИСТИКА ИЗВЛЕЧЕННЫХ ДАННЫХ")
    print("="*60)
    print(f"Обработано JSON записей: {total_records}")
    print(f"Статусов: {stats['statuses']}")
    print(f"Способов создания: {stats['creation_methods']}")
    print(f"Типов объектов: {stats['entity_types']}")
    print(f"Органов: {stats['authorities']}")
    print(f"Способов ликвидации: {stats['liquidation_methods']}")
    
    # Подключение к БД
    print("\n" + "="*60)
    print("🔌 ПОДКЛЮЧЕНИЕ К БАЗЕ ДАННЫХ")
    print("="*60)
    print(f"Host: {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    print(f"Database: {DB_CONFIG['dbname']}")
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("✅ Подключение установлено")
        
        # Вставка данных
        insert_to_database(conn, extractor)
        
        conn.close()
        
        print("\n" + "="*60)
        print("✅ ЗАГРУЗКА ЗАВЕРШЕНА УСПЕШНО!")
        print("="*60)
        
    except Exception as e:
        print(f"❌ Ошибка при работе с БД: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()





