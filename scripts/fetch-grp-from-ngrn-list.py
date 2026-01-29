#!/usr/bin/env python3
"""
Скрипт для загрузки данных ГРП из списка УНП в файле ngrm_list.txt.

Этот скрипт:
1. Читает список УНП из файла ngrm_list.txt
2. Загружает данные о налогоплательщиках из GRP API для этих УНП
3. Сохраняет в JSON файл
4. JSON можно потом быстро загрузить в БД без API запросов

Особенности:
- Использует пагинацию для обработки большого количества УНП
- Поддерживает перезапись существующих данных
- Показывает прогресс обработки
"""
import sys
import os
import asyncio
import json
from datetime import datetime
from app.core.logger import get_logger
from app.services.grp_client import GRPClient

logger = get_logger("fetch_grp_from_ngrn_list")


def read_unps_from_file(filepath: str, limit: int = None) -> list:
    """Read UNPs from ngrm_list.txt file"""
    unps = []

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    with open(filepath, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue

            try:
                unp = int(line)
                unps.append(unp)

                if limit and len(unps) >= limit:
                    break
            except ValueError:
                logger.warning(f"Invalid UNP format on line {line_num}: {line}")
                continue

    return unps


def process_unps_from_file(filepath: str, limit: int = None, page_size: int = 1000,
                          only_missing: bool = False, force_refresh: bool = False):
    """
    Process UNPs from file and fetch GRP data

    Args:
        filepath: Path to ngrm_list.txt file
        limit: Maximum number of UNPs to process
        page_size: Number of UNPs per page
        only_missing: Only fetch UNPs not in database
        force_refresh: Force refresh existing data
    """

    # Read UNPs from file
    logger.info(f"Reading UNPs from file: {filepath}")
    try:
        file_unps = read_unps_from_file(filepath, limit)
        logger.info(f"Found {len(file_unps)} UNPs in file")
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        sys.exit(1)

    if not file_unps:
        logger.warning("No valid UNPs found in file")
        return

    # Limit processing if specified
    actual_limit = min(limit, len(file_unps)) if limit else len(file_unps)
    unps_to_process = file_unps[:actual_limit]

    logger.info(f"Will process {len(unps_to_process)} UNPs with page_size={page_size}")

    # Calculate total pages
    total_pages = (len(unps_to_process) + page_size - 1) // page_size
    logger.info(f"Total pages to process: {total_pages}")

    # Process in pages
    for page in range(total_pages):
        page_start = page * page_size
        page_end = min(page_start + page_size, len(unps_to_process))
        page_unps = unps_to_process[page_start:page_end]

        logger.info(f"Processing page {page + 1}/{total_pages}: UNPs {page_start + 1}-{page_end}")

        try:
            # Create a temporary task to process this page
            # We'll modify the fetch_grp_to_json to accept a list of UNPs instead
            count = fetch_grp_to_json_for_unp_list(page_unps, only_missing=only_missing)
            logger.info(f"Page {page + 1} completed: processed {count} UNPs")

        except Exception as e:
            logger.error(f"Error processing page {page + 1}: {e}")
            # Continue with next page instead of stopping
            continue

    logger.info("All pages processed successfully!")


def fetch_grp_to_json_for_unp_list(unps: list, only_missing: bool = True, output_dir: str = "data/grp_json"):
    """
    Fetch GRP data for a provided list of UNPs and save to JSON
    """

    async def _fetch():
        client = GRPClient()
        taxpayers_data = []

        try:
            logger.info(f"📥 Fetching GRP data for {len(unps)} provided UNPs")

            successful_fetches = 0
            max_retries = 3
            base_delay = 1.15
            concurrency_limit = 4

            async def fetch_single_unp(unp: int):
                nonlocal successful_fetches

                retry_count = 0
                while retry_count < max_retries:
                    try:
                        result = await client.get_taxpayer(unp)

                        if result and isinstance(result, dict):
                            taxpayer_record = {
                                "unp": unp,
                                **result
                            }
                            taxpayers_data.append(taxpayer_record)
                            successful_fetches += 1
                            return f"✅ UNP {unp}"
                        else:
                            logger.warning(f"Empty or invalid data returned for UNP {unp}: {result}")
                            return f"⚠️ UNP {unp} - empty data"
                        break

                    except Exception as e:
                        retry_count += 1
                        error_msg = str(e) or "Unknown error"

                        if "429" in error_msg:
                            delay = base_delay * (2 ** retry_count)
                            logger.warning(f"Rate limit hit for UNP {unp}, retry {retry_count}/{max_retries} after {delay}s")
                            if retry_count < max_retries:
                                await asyncio.sleep(delay)
                                continue
                        elif "Server disconnected" in error_msg or "timeout" in error_msg.lower():
                            delay = base_delay * retry_count
                            logger.warning(f"Connection issue for UNP {unp}, retry {retry_count}/{max_retries}")
                            if retry_count < max_retries:
                                await asyncio.sleep(delay)
                                continue
                        elif "404" in error_msg or "Not Found" in error_msg:
                            logger.warning(f"UNP {unp} not found in GRP")
                            return f"❌ UNP {unp} - not found"
                        else:
                            logger.warning(f"Failed to fetch GRP data for UNP {unp}: {error_msg}")
                            return f"❌ UNP {unp} - error"
                        break

                return f"❌ UNP {unp} - failed after retries"

            # Process with controlled concurrency
            semaphore = asyncio.Semaphore(concurrency_limit)

            async def fetch_with_semaphore(unp):
                async with semaphore:
                    result = await fetch_single_unp(unp)
                    await asyncio.sleep(base_delay)
                    return result

            # Process all UNPs
            tasks = [fetch_with_semaphore(unp) for unp in unps]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Log results summary
            success_count = sum(1 for r in results if isinstance(r, str) and r.startswith("✅"))
            error_count = sum(1 for r in results if isinstance(r, str) and r.startswith("❌"))
            warning_count = sum(1 for r in results if isinstance(r, str) and r.startswith("⚠️"))

            logger.info(f"Processing completed: ✅ {success_count} successful, ⚠️ {warning_count} warnings, ❌ {error_count} errors")

        except Exception as e:
            logger.error(f"❌ Error in fetch_grp_to_json_for_unp_list: {e}")
            raise
        finally:
            await client.close()

        # Save to JSON file
        if taxpayers_data:
            os.makedirs(output_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"grp_taxpayers_from_ngrn_list_{timestamp}.json"
            filepath = os.path.join(output_dir, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(taxpayers_data, f, ensure_ascii=False, indent=2)

            logger.info(f"✅ Saved to {filepath}")
            logger.info(f"   File size: {os.path.getsize(filepath) / 1024 / 1024:.2f} MB")
            logger.info(f"   Total taxpayers: {len(taxpayers_data)}")
        else:
            logger.info("No data to save")
            return 0

        return len(taxpayers_data)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_fetch())
    finally:
        loop.close()


def main():
    print("=" * 90)
    print(" " * 15 + "ЗАГРУЗКА ДАННЫХ ГРП ИЗ СПИСКА УНП В ngrm_list.txt")
    print("=" * 90)
    print()
    print("Этот скрипт читает УНП из файла ngrm_list.txt и загружает")
    print("данные о налогоплательщиках из GRP API.")
    print()
    print("⚠️  ВНИМАНИЕ: GRP API имеет ограничения на частоту запросов!")
    print("   Загрузка происходит с пагинацией и параллельной обработкой.")
    print()

    # Path to ngrn_list.txt
    ngrn_file = "ngrn_list.txt"
    if not os.path.exists(ngrn_file):
        print(f"❌ Файл {ngrn_file} не найден в текущей директории")
        sys.exit(1)

    # Спросить параметры загрузки
    print("Выберите объем загрузки:")
    print("  1. Маленький тест (100 УНП)")
    print("  2. Средний (1000 УНП)")
    print("  3. Большой (10000 УНП)")
    print("  4. Очень большой (50000 УНП)")
    print("  5. Весь файл (все УНП из ngrm_list.txt)")
    print()

    choice = input("Ваш выбор (1-5): ").strip()

    if choice == "1":
        limit = 100
    elif choice == "2":
        limit = 1000
    elif choice == "3":
        limit = 10000
    elif choice == "4":
        limit = 50000
    elif choice == "5":
        limit = None  # Все УНП
    else:
        print("❌ Неверный выбор")
        sys.exit(1)

    print()
    print("Что делать с существующими данными?")
    print("  1. Только недостающие (пропустить существующие)")
    print("  2. Перезаписать все (обновить существующие)")
    print()

    mode_choice = input("Ваш выбор (1-2, Enter = 1): ").strip() or "1"
    only_missing = mode_choice == "1"

    print()
    print("Размер страницы (количество УНП за раз):")
    print("  1. Маленький (500)")
    print("  2. Средний (1000) - рекомендуется")
    print("  3. Большой (1500)")
    print()

    page_choice = input("Ваш выбор (1-3, Enter = 2): ").strip() or "2"

    if page_choice == "1":
        page_size = 1000
    elif page_choice == "2":
        page_size = 2000
    elif page_choice == "3":
        page_size = 3000
    else:
        print("❌ Неверный выбор")
        sys.exit(1)

    print()
    limit_text = f"{limit}" if limit else "все"
    print(f"Настройки:")
    print(f"  Файл: {ngrn_file}")
    print(f"  Лимит УНП: {limit_text}")
    print(f"  Режим: {'только недостающие' if only_missing else 'перезаписать все'}")
    print(f"  Размер страницы: {page_size}")
    print()

    # Calculate estimated time
    if limit:
        estimated_seconds = (limit / 3) * 1.5  # 3 concurrent requests
        estimated_minutes = estimated_seconds / 60
        if estimated_minutes > 60:
            estimated_hours = estimated_minutes / 60
            time_est = f"~{estimated_hours:.1f} часов"
        else:
            time_est = f"~{estimated_minutes:.0f} минут"
        print(f"⚠️  Ориентировочное время: {time_est}")
        print()

    response = input("Начать загрузку? (yes/no): ")
    if response.lower() != "yes":
        print("❌ Отменено")
        sys.exit(0)

    print()
    logger.info("🚀 Начинаю загрузку данных ГРП из списка УНП...")

    try:
        process_unps_from_file(
            filepath=ngrn_file,
            limit=limit,
            page_size=page_size,
            only_missing=only_missing,
            force_refresh=not only_missing
        )

        print()
        print("=" * 80)
        logger.info("🎉 ЗАГРУЗКА ЗАВЕРШЕНА!")
        logger.info("   JSON файлы сохранены в: data/grp_json/")
        logger.info("")
        logger.info("Для загрузки данных в БД выполните:")
        logger.info("   python scripts/load_grp_json.py --sync")
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