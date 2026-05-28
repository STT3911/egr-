"""Compare two park.by residents JSON snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two park.by resident snapshots")
    parser.add_argument("old_json", type=Path)
    parser.add_argument("new_json", type=Path)
    parser.add_argument("--output", type=Path, default=None, help="Optional path for full diff JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    from app.services.park_residents import diff_snapshot_rows, load_snapshot

    diff = diff_snapshot_rows(load_snapshot(args.old_json), load_snapshot(args.new_json))
    summary = {
        "old_count": diff["old_count"],
        "new_count": diff["new_count"],
        "added": len(diff["added"]),
        "removed": len(diff["removed"]),
        "changed": len(diff["changed"]),
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")
        summary["output"] = str(args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
