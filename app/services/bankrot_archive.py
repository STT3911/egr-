"""Lossless Bankrot exports: shared manager blobs, gzip and bounded retention.

Database business rows are never modified by this module. Legacy JSONL and
mixed resumable files remain readable. Only completed exports may be archived.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

_NAME = re.compile(r"^(bankrot_cases_\d+_\d{8}_\d{6})\.jsonl(?:\.tmp|\.gz)?$")
_BLOB = re.compile(r"^[a-f0-9]{64}\.json\.gz$")


def _stem(path: Path) -> str:
    match = _NAME.fullmatch(path.name)
    if not match or path.is_symlink():
        raise ValueError("Unsafe Bankrot archive path")
    return match.group(1)


def _encode(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _fsync_directory(path: Path):
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _hash_file(path: Path, *, compressed=False) -> str:
    digest = hashlib.sha256()
    opener = gzip.open if compressed else open
    with opener(path, "rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class BankrotArchiveWriter:
    """Append compact records; manager blobs become durable before references."""
    def __init__(self, path: Path, mode: str):
        self.path = Path(path)
        self.entities = self.path.parent / (_stem(self.path) + ".managers")
        if self.entities.is_symlink() or mode not in {"a", "w"}:
            raise ValueError("Unsafe Bankrot writer configuration")
        self.mode = mode
        self._known = set()

    def __enter__(self):
        self.stream = self.path.open(self.mode, encoding="utf-8")
        _fsync_directory(self.path.parent)
        return self

    def __exit__(self, *_):
        self.stream.close()

    def flush(self):
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def write_record(self, record):
        related = record.get("related_data") or {}
        managers = {key: value for key, value in related.items() if key.startswith("manager_")}
        compact = dict(record)
        if managers:
            payload = _encode(managers)
            digest = hashlib.sha256(payload).hexdigest()
            created_directory = not self.entities.exists()
            self.entities.mkdir(exist_ok=True)
            if self.entities.is_symlink():
                raise ValueError("Unsafe manager blob directory")
            if created_directory:
                _fsync_directory(self.path.parent)
            destination = self.entities / (digest + ".json.gz")
            if destination.is_symlink():
                raise ValueError("Unsafe manager blob path")
            if digest not in self._known:
                if destination.exists():
                    if _hash_file(destination, compressed=True) != digest:
                        raise ValueError("Corrupt existing manager blob")
                else:
                    fd, name = tempfile.mkstemp(prefix=".manager-", dir=self.entities)
                    temporary = Path(name)
                    try:
                        with os.fdopen(fd, "wb") as stream:
                            with gzip.GzipFile(fileobj=stream, mode="wb", compresslevel=3, mtime=0) as zipped:
                                zipped.write(payload)
                            stream.flush()
                            os.fsync(stream.fileno())
                        temporary.chmod(self.path.stat().st_mode & 0o777)
                        os.replace(temporary, destination)
                        _fsync_directory(self.entities)
                    finally:
                        temporary.unlink(missing_ok=True)
                self._known.add(digest)
            compact["archive_version"] = 2
            compact["manager_data_ref"] = digest
            compact["related_data"] = {key: value for key, value in related.items() if key not in managers}
        self.stream.write(_encode(compact).decode("utf-8") + "\n")


def iter_bankrot_archive(path: Path):
    """Restore complete records from legacy JSONL, mixed .tmp or new gzip."""
    path = Path(path)
    entities = path.parent / (_stem(path) + ".managers")
    if entities.is_symlink():
        raise ValueError("Unsafe manager blob directory")
    opener = gzip.open if path.name.endswith(".gz") else open
    # Small cache only: archive restoration must not load all manager data in RAM.
    cache = {}
    with opener(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            record = json.loads(line)
            digest = record.pop("manager_data_ref", None)
            if digest is not None:
                if record.pop("archive_version", None) != 2 or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                    raise ValueError("Invalid manager reference")
                if digest not in cache:
                    blob = entities / (digest + ".json.gz")
                    if blob.is_symlink():
                        raise ValueError("Unsafe manager blob path")
                    with gzip.open(blob, "rb") as manager_stream:
                        raw = manager_stream.read()
                    if hashlib.sha256(raw).hexdigest() != digest:
                        raise ValueError("Corrupt manager blob")
                    managers = json.loads(raw)
                    if not isinstance(managers, dict) or any(not key.startswith("manager_") for key in managers):
                        raise ValueError("Invalid manager blob schema")
                    if len(cache) >= 8:
                        cache.clear()
                    cache[digest] = managers
                related = record.setdefault("related_data", {})
                if not isinstance(related, dict) or set(related).intersection(cache[digest]):
                    raise ValueError("Conflicting manager reference")
                record["related_data"] = {**related, **cache[digest]}
            yield record


def compress_completed_archive(path: Path, *, before_remove=None) -> Path:
    """Verify CRC + uncompressed SHA256; commit metadata before removing original.

If a prior compression/DB commit failed, retry safely without overwriting an
existing conflicting archive. Only the caller may certify completion in DB.
"""
    path = Path(path)
    _stem(path)
    if not path.name.endswith(".jsonl") or not path.is_file():
        raise ValueError("Only completed JSONL files may be compressed")
    initial = path.stat()
    identity = (initial.st_ino, initial.st_size, initial.st_mtime_ns)
    destination = path.with_name(path.name + ".gz")
    if destination.is_symlink():
        raise ValueError("Unsafe compressed archive path")
    digest = _hash_file(path)
    if not destination.exists():
        fd, name = tempfile.mkstemp(prefix=".bankrot-compress-", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb") as output:
                with gzip.GzipFile(fileobj=output, mode="wb", compresslevel=3, mtime=0) as zipped, path.open("rb") as source:
                    shutil.copyfileobj(source, zipped, length=1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
            if _hash_file(temporary, compressed=True) != digest:
                raise ValueError("Compressed archive verification failed")
            temporary.chmod(initial.st_mode & 0o777)
            os.replace(temporary, destination)
            _fsync_directory(path.parent)
        finally:
            temporary.unlink(missing_ok=True)
    elif _hash_file(destination, compressed=True) != digest:
        raise ValueError("Conflicting compressed archive; original preserved")
    current = path.stat()
    if (current.st_ino, current.st_size, current.st_mtime_ns) != identity:
        raise ValueError("Archive changed during compression; original preserved")
    if before_remove:
        before_remove(destination, {"source_sha256": digest, "source_bytes": initial.st_size,
                                    "compressed_bytes": destination.stat().st_size})
    path.unlink()
    _fsync_directory(path.parent)
    return destination


def maintain_bankrot_archives(db, output_dir: Path, *, keep: int = 0, only_run_id=None, progress=None):
    """Compress DB-certified completed runs; pruning is opt-in (keep=0 disables)."""
    from sqlalchemy import text
    with db.get_bind().begin() as lock:
        if not lock.execute(text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"),
                            {"key": "bankrot:archive_maintenance"}).scalar():
            return {"status": "already_running", "compressed": 0, "pruned": 0, "bytes_released": 0}
        return _maintain_bankrot_archives(db, output_dir, keep=keep, only_run_id=only_run_id, progress=progress)


def _maintain_bankrot_archives(db, output_dir: Path, *, keep: int, only_run_id=None, progress=None):
    from datetime import datetime
    from app.database.models import BankrotSyncRun
    root = Path(output_dir).resolve()
    if Path(output_dir).is_symlink() or keep < 0:
        raise ValueError("Unsafe Bankrot archive policy")
    runs = db.query(BankrotSyncRun).filter(
        BankrotSyncRun.status == "done", BankrotSyncRun.failed_cases == 0,
        BankrotSyncRun.finished_at.isnot(None),
    ).order_by(BankrotSyncRun.finished_at.desc(), BankrotSyncRun.id.desc()).all()
    result = {"compressed": 0, "pruned": 0, "bytes_released": 0}
    for run in runs:
        if run.status != 'done' or run.failed_cases or run.finished_at is None:
            continue
        if only_run_id is not None and run.id != only_run_id:
            continue
        if not run.output_file:
            continue
        path = Path(run.output_file)
        if path.parent.resolve() != root or path.is_symlink() or _stem(path).split('_')[2] != str(run.id):
            raise ValueError("Archive outside configured directory")
        if path.name.endswith('.jsonl') and path.exists():
            original_size = path.stat().st_size
            if progress:
                progress({'phase': 'compressing', 'run_id': run.id, 'file': path.name,
                          'source_bytes': original_size})
            def update_output(destination, metadata):
                run.output_file = str(destination)
                run.stats_json = {**(run.stats_json or {}), "archive": metadata,
                                  "output_file": str(destination)}
                db.commit()
            compressed = compress_completed_archive(path, before_remove=update_output)
            result['compressed'] += 1
            result['bytes_released'] += original_size - compressed.stat().st_size
            if progress:
                progress({'phase': 'compressed', 'run_id': run.id, 'file': compressed.name,
                          'compressed_bytes': compressed.stat().st_size,
                          'bytes_released': original_size - compressed.stat().st_size})
    if keep:
        # Failed child datasets are not a good replacement for an older complete
        # snapshot, even if the overall import finished without failed cases.
        eligible = [run for run in runs if run.status == 'done' and not run.failed_cases
                    and run.finished_at is not None and not (run.stats_json or {}).get('datasets_failed')
                    and run.output_file and Path(run.output_file).is_file()
                    and Path(run.output_file).name.endswith('.jsonl.gz')]
        for run in eligible[keep:]:
            if not run.output_file:
                continue
            path = Path(run.output_file)
            if path.parent.resolve() != root or path.is_symlink():
                raise ValueError('Archive outside configured directory')
            if not path.exists() or not path.name.endswith('.jsonl.gz'):
                continue
            if _stem(path).split('_')[2] != str(run.id):
                raise ValueError('Wrong archive run identity')
            # Verify all records/references before considering this archive disposable.
            for _ in iter_bankrot_archive(path):
                pass
            entities = root / (_stem(path) + '.managers')
            blobs = list(entities.iterdir()) if entities.exists() else []
            if entities.is_symlink() or any(p.is_symlink() or not p.is_file() or not _BLOB.fullmatch(p.name) for p in blobs):
                raise ValueError('Unexpected manager directory contents; archive preserved')
            size = path.stat().st_size + sum(p.stat().st_size for p in blobs)
            # Persist the deliberate file-only removal, never delete DB cases/datasets.
            run.stats_json = {**(run.stats_json or {}), 'archive_pruned_at': datetime.utcnow().isoformat()}
            run.output_file = None
            db.commit()
            path.unlink()
            for blob in blobs:
                blob.unlink()
            if entities.exists():
                entities.rmdir()
            _fsync_directory(root)
            result['pruned'] += 1
            result['bytes_released'] += size
    return result
