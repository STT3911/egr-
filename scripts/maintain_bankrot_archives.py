"""Verify and compress completed Bankrot files; preserve all snapshots by default."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.core.database import SessionLocal
from app.database.models import BankrotSyncRun
from app.services.bankrot_archive import maintain_bankrot_archives


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path(settings.BANKROT_OUTPUT_DIR))
    parser.add_argument('--apply', action='store_true', help='Compress after byte-for-byte verification; otherwise show plan only')
    parser.add_argument('--only-run', type=int)
    parser.add_argument('--keep', type=int, default=0, help='0 keeps all completed archives (default)')
    parser.add_argument('--allow-prune', action='store_true', help='Explicitly authorize deleting older completed archives')
    args = parser.parse_args()
    if args.keep < 0 or (args.keep and not args.allow_prune):
        parser.error('Positive --keep requires explicit --allow-prune; 0 keeps all snapshots')
    if hasattr(os, 'nice'):
        os.nice(15)
    with SessionLocal() as db:
        if not args.apply:
            rows = db.query(BankrotSyncRun).filter(BankrotSyncRun.status == 'done',
                BankrotSyncRun.failed_cases == 0).order_by(BankrotSyncRun.finished_at.desc()).all()
            files = [Path(r.output_file) for r in rows if r.output_file and (args.only_run is None or r.id == args.only_run)]
            files = [p for p in files if p.parent.resolve() == args.output_dir.resolve() and p.exists() and not p.is_symlink()]
            print(json.dumps({'mode':'plan','keep':args.keep,'files':[p.name for p in files]}))
        else:
            progress = lambda item: print(json.dumps(item), flush=True)
            result = maintain_bankrot_archives(db, args.output_dir, keep=args.keep,
                                               only_run_id=args.only_run, progress=progress)
            print(json.dumps({'phase':'complete', **result}), flush=True)


if __name__ == '__main__':
    main()
