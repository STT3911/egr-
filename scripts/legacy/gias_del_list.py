import requests
import json
import time

def fetch_all_locked_suppliers(base_url, page_size=40, q_param='{}'):
    """
    Загружает все страницы с заблокированными поставщиками.
    
    :param base_url: базовый URL эндпоинта
    :param page_size: количество элементов на странице (должно совпадать с API)
    :param q_param: значение параметра q (фильтр), по умолчанию '{}'
    :return: список всех записей
    """
    all_data = []
    page = 0

    while True:
        params = {
            'q': q_param,
            'page': page,
            'size': page_size
        }

        try:
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"Ошибка запроса на странице {page}: {e}")
            break
        except json.JSONDecodeError as e:
            print(f"Ошибка парсинга JSON на странице {page}: {e}")
            break

        # Извлекаем список элементов в зависимости от структуры ответа
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # Пробуем наиболее частые ключи для списка данных
            if 'content' in data:
                items = data['content']
            elif 'data' in data:
                items = data['data']
            elif 'items' in data:
                items = data['items']
            elif 'results' in data:
                items = data['results']
            else:
                print(f"Не удалось определить структуру данных на странице {page}, ключи: {list(data.keys())}")
                # Если не нашли список, возможно, это одиночный объект – прекращаем
                break
        else:
            print(f"Неожиданный тип данных: {type(data)}")
            break

        if not items:  # пустой список – данные закончились
            print(f"Страница {page} пуста, завершаем.")
            break

        all_data.extend(items)
        print(f"Страница {page} загружена, получено {len(items)} записей. Всего: {len(all_data)}")

        # Условия остановки:
        # 1. Получено меньше элементов, чем запрошено (последняя неполная страница)
        if len(items) < page_size:
            print("Последняя страница (меньше запрошенного размера).")
            break

        # 2. Если API возвращает информацию о пагинации в самом ответе
        if isinstance(data, dict):
            if 'totalPages' in data and page + 1 >= data['totalPages']:
                print("Достигнута последняя страница согласно totalPages.")
                break
            if 'totalElements' in data and len(all_data) >= data['totalElements']:
                print("Собраны все элементы согласно totalElements.")
                break

        page += 1
        time.sleep(0.5)  # небольшая задержка, чтобы не нагружать сервер

    return all_data


if __name__ == "__main__":
    url = "https://gias.by/directory/api/v1/locked_suppliers/page"
    suppliers = fetch_all_locked_suppliers(url, page_size=40, q_param='{}')

    if suppliers:
        filename = "data/imports/locked_suppliers/locked_suppliers.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(suppliers, f, ensure_ascii=False, indent=2)
        print(f"Сохранено {len(suppliers)} записей в файл {filename}")
    else:
        print("Не удалось получить данные.")
