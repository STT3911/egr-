#!/usr/bin/env python3
"""
Разбить большой JSON-файл (массив объектов) на части по ~N МБ без загрузки всего в память.

Использование:
  python scripts/split-large-json.py data/egr_json_full/31-12-1989-30-12-2025.json
  python scripts/split-large-json.py path/to/file.json --size-mb 150 --out-dir data/egr_json_full

После разбиения можно удалить исходный файл и запустить импорт — обработаются все части.
"""
import os
import sys
import json
import argparse

# Корень проекта
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def main():
    parser = argparse.ArgumentParser(description="Split large JSON array file into smaller files (streaming)")
    parser.add_argument("file", help="Path to large .json file (root must be array [...])")
    parser.add_argument("--size-mb", type=int, default=100,
                        help="Max size of each output file in MB (default: 100)")
    parser.add_argument("--out-dir", default=None,
                        help="Output directory (default: same as input file)")
    parser.add_argument("--prefix", default=None,
                        help="Output filename prefix (default: original name without .json)")
    args = parser.parse_args()

    file_path = os.path.abspath(args.file)
    if not os.path.isfile(file_path):
        print(f"File not found: {file_path}")
        sys.exit(1)

    out_dir = args.out_dir or os.path.dirname(file_path)
    os.makedirs(out_dir, exist_ok=True)
    base_name = args.prefix or os.path.splitext(os.path.basename(file_path))[0]
    target_bytes = args.size_mb * 1024 * 1024

    try:
        import ijson
    except ImportError:
        print("Install ijson: pip install ijson")
        sys.exit(1)

    # Определить путь по первым байтам (без потребления данных)
    with open(file_path, "rb") as f:
        peek = f.read(512)
    peek_str = peek.decode("utf-8", errors="ignore").strip()
    if peek_str.startswith("["):
        found_path = "item"
    elif peek_str.startswith("{"):
        if '"data"' in peek_str[:100] or "'data'" in peek_str[:100]:
            found_path = "data.item"
        elif '"items"' in peek_str[:100] or "'items'" in peek_str[:100]:
            found_path = "items.item"
        else:
            found_path = "data.item"  # частый случай
    else:
        print("Unknown JSON structure (expected root [...] or {\"data\": [...]}).")
        sys.exit(1)

    print(f"Input: {file_path} ({os.path.getsize(file_path) / (1024*1024):.1f} MB)")
    print(f"Output dir: {out_dir}, ~{args.size_mb} MB per file, path: {found_path}")
    print()

    part = 0
    current_file = None
    current_count = 0
    current_size = 0
    total_items = 0

    with open(file_path, "rb") as fh:
        for item in ijson.items(fh, found_path):
            if not isinstance(item, dict):
                continue
            raw = json.dumps(item, ensure_ascii=False)
            item_len = len(raw.encode("utf-8")) + 2  # +2 для запятой и перевода строки
            if current_file is None or (current_count > 0 and current_size + item_len > target_bytes):
                if current_file is not None:
                    current_file.write("\n]")
                    current_file.close()
                    print(f"   Part {part}: {current_count} items, {current_size / (1024*1024):.1f} MB")
                part += 1
                out_name = f"{base_name}_part{part:03d}.json"
                out_path = os.path.join(out_dir, out_name)
                current_file = open(out_path, "w", encoding="utf-8")
                current_file.write("[\n")
                current_count = 0
                current_size = 0

            if current_count > 0:
                current_file.write(",\n")
            current_file.write(raw)
            current_count += 1
            current_size += item_len
            total_items += 1

            if total_items % 50000 == 0 and total_items > 0:
                print(f"   Processed {total_items} items...")

    if current_file is not None:
        current_file.write("\n]")
        current_file.close()
        print(f"   Part {part}: {current_count} items, {current_size / (1024*1024):.1f} MB")

    print()
    print(f"Done. {total_items} items in {part} file(s).")
    print(f"Next: move or remove original file, then run import (e.g. python auto-import-data.py)")


if __name__ == "__main__":
    main()
