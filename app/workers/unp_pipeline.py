from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.telegram_alerts import send_telegram_alert
from app.services.unp_enum import SEQ_MAX


logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("egr_aggregator.unp_pipeline")


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class StatusStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.data: dict[str, Any] = {
            "version": 1,
            "pid": os.getpid(),
            "state": "starting",
            "started_at": time.time(),
        }

    def update(self, **values: Any) -> None:
        with self.lock:
            self.data.update(values)
            self.data["updated_at"] = time.time()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
            temporary_path.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary_path, self.path)


class UnpPipeline:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.stop_event = threading.Event()
        self.status = StatusStore(Path(args.status_path).resolve())
        self.pipeline_lock = threading.Lock()
        self.last_gov_rebuild_at = time.time()
        self.maintenance_thread: threading.Thread | None = None
        self.lock_file = None
        self.failed = False
        self.completed = False
        self.last_progress_alert_at = 0.0
        self.last_retry_alert_at = 0.0
        self.last_maintenance_error_alert_at = 0.0

    def request_stop(self, signum=None, frame=None) -> None:
        logger.info("Stop requested")
        self.stop_event.set()

    def _alert_throttled(
        self,
        text: str,
        *,
        timestamp_attribute: str,
        interval: float | None = None,
    ) -> None:
        now = time.time()
        minimum_interval = interval or self.args.alert_interval
        last_sent_at = float(getattr(self, timestamp_attribute, 0.0))
        if now - last_sent_at < minimum_interval:
            return
        if send_telegram_alert(text):
            setattr(self, timestamp_attribute, now)

    def _send_progress_alert(self) -> None:
        checkpoint_path = Path(self.args.checkpoint_path).resolve()
        try:
            checkpoint = json.loads(
                checkpoint_path.read_text(encoding="utf-8-sig")
            )
        except Exception:
            return
        with self.status.lock:
            pipeline_status = dict(self.status.data)
        last_sync = pipeline_status.get("last_sync") or {}

        self._alert_throttled(
            "⏳ Перебор УНП работает\n"
            f"Регион: {checkpoint.get('region', '-')}\n"
            f"Последний УНП: {checkpoint.get('last_unp', '-')}\n"
            f"Следующий УНП: {checkpoint.get('next_unp', '-')}\n"
            f"Запросов: {checkpoint.get('queried', 0)}\n"
            f"Найдено: {checkpoint.get('found', 0)}\n"
            f"Не найдено: {checkpoint.get('misses', 0)}\n"
            f"Ошибок: {checkpoint.get('errors', 0)}\n"
            f"Распарсено за последний цикл: {pipeline_status.get('last_parsed', 0)}\n"
            f"Компаний добавлено: {last_sync.get('companies_added', 0)}",
            timestamp_attribute="last_progress_alert_at",
        )

    def _acquire_lock(self) -> None:
        import fcntl

        lock_path = Path(self.args.lock_path).resolve()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_file = lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"Another UNP pipeline already holds {lock_path}") from exc
        self.lock_file.seek(0)
        self.lock_file.truncate()
        self.lock_file.write(str(os.getpid()))
        self.lock_file.flush()

    def _run_pipeline_cycle(self, force_sync: bool = False) -> None:
        from app.services.company_registry import sync_companies_from_grp
        from app.tasks.sync_tasks import grp_process_raw

        if not self.pipeline_lock.acquire(blocking=False):
            return

        try:
            cycle_started_at = time.time()
            parsed_total = 0
            self.status.update(
                maintenance_state="processing_raw",
                pipeline_cycle_started_at=cycle_started_at,
            )

            for batch_number in range(1, self.args.max_process_batches + 1):
                if self.stop_event.is_set():
                    break
                parsed = int(grp_process_raw(limit=self.args.process_batch) or 0)
                parsed_total += parsed
                self.status.update(
                    maintenance_state="processing_raw",
                    process_batch_number=batch_number,
                    parsed_in_cycle=parsed_total,
                )
                if parsed < self.args.process_batch:
                    break

            if self.stop_event.is_set():
                return

            sync_stats = {"companies_added": 0, "names_added": 0}
            if parsed_total or force_sync:
                self.status.update(maintenance_state="syncing_companies")
                sync_stats = sync_companies_from_grp()
            now = time.time()
            has_new_data = bool(
                parsed_total
                or sync_stats.get("companies_added")
                or sync_stats.get("names_added")
            )
            rebuild_due = (
                self.args.gov_rebuild_enabled
                and has_new_data
                and now - self.last_gov_rebuild_at
                >= self.args.gov_rebuild_interval
            )
            rebuild_stats: dict[str, Any] | None = None

            if rebuild_due and not self.stop_event.is_set():
                from app.services.gov_organizations import rebuild

                self.status.update(
                    maintenance_state="rebuilding_gov_organizations"
                )
                rebuild_stats = rebuild(
                    include_joint_stock=self.args.include_joint_stock,
                )
                self.last_gov_rebuild_at = time.time()

            self.status.update(
                state="running",
                maintenance_state="idle",
                last_pipeline_at=time.time(),
                last_pipeline_duration_seconds=round(time.time() - cycle_started_at, 3),
                last_parsed=parsed_total,
                last_sync=sync_stats,
                last_gov_rebuild=rebuild_stats,
                last_error=None,
            )
        except Exception as exc:
            logger.exception("Pipeline maintenance cycle failed")
            self.status.update(
                state="running",
                maintenance_state="error",
                last_error=f"{type(exc).__name__}: {exc}",
            )
            self._alert_throttled(
                "❌ Ошибка обработки UNP pipeline\n"
                f"{type(exc).__name__}: {str(exc)[:1500]}",
                timestamp_attribute="last_maintenance_error_alert_at",
            )
        finally:
            self.pipeline_lock.release()

    def _maintenance_loop(self) -> None:
        first_cycle = True
        while not self.stop_event.is_set():
            self._run_pipeline_cycle(force_sync=first_cycle)
            first_cycle = False
            self._send_progress_alert()
            if self.stop_event.wait(self.args.process_interval):
                break

    def _build_enumerator_args(self) -> argparse.Namespace:
        from scripts import unp_enumerate

        arguments = [
            "--regions",
            self.args.regions,
            "--seq-start",
            str(self.args.seq_start),
            "--seq-end",
            str(self.args.seq_end),
            "--empty-stop",
            str(self.args.empty_stop),
            "--concurrency",
            str(self.args.concurrency),
            "--candidate-batch",
            str(self.args.candidate_batch),
            "--delay",
            str(self.args.delay),
            "--flush-every",
            str(self.args.flush_every),
            "--progress-every",
            str(self.args.progress_every),
            "--checkpoint-every",
            str(self.args.checkpoint_every),
            "--checkpoint-path",
            self.args.checkpoint_path,
            "--known-tables",
            self.args.known_tables,
            "--scan-mode",
            self.args.scan_mode,
            "--frontier-lookahead",
            str(self.args.frontier_lookahead),
            "--frontier-backtrack",
            str(self.args.frontier_backtrack),
            "--range-gap",
            str(self.args.range_gap),
            "--registry-refresh-interval",
            str(self.args.registry_refresh_interval),
            "--resume",
        ]
        return unp_enumerate.build_argparser().parse_args(arguments)

    def run(self) -> int:
        from scripts import unp_enumerate

        self._acquire_lock()
        unp_enumerate.CHECKPOINT_PATH = str(Path(self.args.checkpoint_path).resolve())
        enumerator_args = self._build_enumerator_args()
        self.status.update(
            state="running",
            enumeration_state="starting",
            checkpoint_path=unp_enumerate.CHECKPOINT_PATH,
            regions=self.args.regions,
            scan_mode=self.args.scan_mode,
            seq_start=self.args.seq_start,
            seq_end=self.args.seq_end,
            empty_stop=self.args.empty_stop,
        )
        send_telegram_alert(
            "🚀 UNP pipeline запущен\n"
            f"Режим: {self.args.scan_mode}\n"
            f"Регионы: {self.args.regions}\n"
            f"Диапазон seq: {self.args.seq_start}–{self.args.seq_end}"
        )
        self.last_progress_alert_at = time.time()

        self.maintenance_thread = threading.Thread(
            target=self._maintenance_loop,
            name="unp-pipeline-maintenance",
        )
        self.maintenance_thread.start()

        try:
            while not self.stop_event.is_set():
                self.status.update(
                    state="running",
                    enumeration_state="enumerating",
                    enumeration_started_at=time.time(),
                )
                outcome = asyncio.run(
                    unp_enumerate.run(
                        enumerator_args,
                        stop_event=self.stop_event,
                    )
                )
                self.status.update(
                    state="running",
                    enumeration_state=outcome,
                    enumeration_finished_at=time.time(),
                )

                if outcome == "retry":
                    self._alert_throttled(
                        "🔁 Перебор УНП остановлен на временной ошибке\n"
                        f"Повтор через {self.args.retry_delay:g} сек.",
                        timestamp_attribute="last_retry_alert_at",
                    )
                    if self.stop_event.wait(self.args.retry_delay):
                        break
                    continue

                if outcome == "completed":
                    self._run_pipeline_cycle(force_sync=True)
                    if self.args.scan_mode == "frontier":
                        self.status.update(
                            state="running",
                            enumeration_state="range_cycle_waiting",
                            next_frontier_scan_at=(
                                time.time() + self.args.frontier_interval
                            ),
                        )
                        if self.stop_event.wait(self.args.frontier_interval):
                            break
                        continue
                    self.completed = True
                    self.status.update(state="completed")
                    send_telegram_alert("🏁 Перебор УНП завершён")
                    while not self.stop_event.wait(1):
                        pass
                break
        except Exception as exc:
            self.failed = True
            self.status.update(
                state="failed",
                last_error=f"{type(exc).__name__}: {exc}",
            )
            logger.exception("UNP pipeline failed")
            send_telegram_alert(
                "💥 UNP pipeline аварийно остановлен\n"
                f"{type(exc).__name__}: {str(exc)[:1500]}"
            )
            raise
        finally:
            self.stop_event.set()
            if self.maintenance_thread is not None:
                self.maintenance_thread.join(timeout=30)
            if not self.failed:
                self.status.update(state="stopped")
                if not self.completed:
                    send_telegram_alert("⏹ UNP pipeline остановлен")

        return 0


def check_health(status_path: str, max_age: float) -> int:
    path = Path(status_path).resolve()
    try:
        status = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        print(f"unhealthy: cannot read {path}: {exc}")
        return 1

    updated_at = float(status.get("updated_at") or 0)
    age = max(0.0, time.time() - updated_at)
    state = str(status.get("state") or "unknown")
    if state == "failed" or age > max_age:
        print(f"unhealthy: state={state} age={age:.1f}s")
        return 1

    print(f"healthy: state={state} age={age:.1f}s")
    return 0


def print_status(status_path: str, checkpoint_path: str) -> int:
    result: dict[str, Any] = {}
    for key, raw_path in (
        ("service", status_path),
        ("enumeration", checkpoint_path),
    ):
        path = Path(raw_path).resolve()
        try:
            result[key] = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            result[key] = {"error": f"{type(exc).__name__}: {exc}", "path": str(path)}
    try:
        from app.services.unp_scan_registry import get_range_scan_cycle_status

        result["range_cycle"] = get_range_scan_cycle_status()
    except Exception as exc:
        result["range_cycle"] = {
            "error": f"{type(exc).__name__}: {exc}",
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autonomous UNP enumeration pipeline")
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument(
        "--status-path",
        default=os.getenv(
            "UNP_PIPELINE_STATUS_PATH",
            "/app/data/unp_pipeline_status.json",
        ),
    )
    parser.add_argument(
        "--checkpoint-path",
        default=os.getenv(
            "UNP_PIPELINE_CHECKPOINT_PATH",
            "/app/data/unp_enumerate_checkpoint.json",
        ),
    )
    parser.add_argument(
        "--lock-path",
        default=os.getenv(
            "UNP_PIPELINE_LOCK_PATH",
            "/app/data/unp_pipeline.lock",
        ),
    )
    parser.add_argument(
        "--regions",
        default=os.getenv("UNP_PIPELINE_REGIONS", "1,2,3,4,5,6,7"),
    )
    parser.add_argument(
        "--scan-mode",
        choices=("frontier", "full"),
        default=os.getenv("UNP_PIPELINE_SCAN_MODE", "frontier"),
    )
    parser.add_argument(
        "--frontier-lookahead",
        type=int,
        default=_env_int("UNP_PIPELINE_FRONTIER_LOOKAHEAD", 50),
    )
    parser.add_argument(
        "--frontier-backtrack",
        type=int,
        default=_env_int("UNP_PIPELINE_FRONTIER_BACKTRACK", 50),
    )
    parser.add_argument(
        "--range-gap",
        type=int,
        default=_env_int("UNP_PIPELINE_RANGE_GAP", 50),
    )
    parser.add_argument(
        "--registry-refresh-interval",
        type=float,
        default=_env_float(
            "UNP_PIPELINE_REGISTRY_REFRESH_INTERVAL_SECONDS",
            86400.0,
        ),
    )
    parser.add_argument(
        "--frontier-interval",
        type=float,
        default=_env_float(
            "UNP_PIPELINE_FRONTIER_INTERVAL_SECONDS",
            5.0,
        ),
    )
    parser.add_argument(
        "--seq-start",
        type=int,
        default=_env_int("UNP_PIPELINE_SEQ_START", 0),
    )
    parser.add_argument(
        "--seq-end",
        type=int,
        default=_env_int("UNP_PIPELINE_SEQ_END", SEQ_MAX),
    )
    parser.add_argument(
        "--empty-stop",
        type=int,
        default=_env_int("UNP_PIPELINE_EMPTY_STOP", 20000),
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=_env_int("UNP_PIPELINE_CONCURRENCY", 2),
    )
    parser.add_argument(
        "--candidate-batch",
        type=int,
        default=_env_int("UNP_PIPELINE_CANDIDATE_BATCH", 500),
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=_env_float("UNP_PIPELINE_DELAY", 2.0),
    )
    parser.add_argument(
        "--flush-every",
        type=int,
        default=_env_int("UNP_PIPELINE_FLUSH_EVERY", 50),
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=_env_int("UNP_PIPELINE_PROGRESS_EVERY", 1000),
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=_env_int("UNP_PIPELINE_CHECKPOINT_EVERY", 20),
    )
    parser.add_argument(
        "--known-tables",
        default=os.getenv(
            "UNP_PIPELINE_KNOWN_TABLES",
            "egr_companies,egr_raw_company_data,grp_raw_data,grp_taxpayer_data",
        ),
    )
    parser.add_argument(
        "--process-batch",
        type=int,
        default=_env_int("UNP_PIPELINE_PROCESS_BATCH", 2000),
    )
    parser.add_argument(
        "--max-process-batches",
        type=int,
        default=_env_int("UNP_PIPELINE_MAX_PROCESS_BATCHES", 10),
    )
    parser.add_argument(
        "--process-interval",
        type=float,
        default=_env_float("UNP_PIPELINE_PROCESS_INTERVAL_SECONDS", 60.0),
    )
    parser.add_argument(
        "--gov-rebuild-enabled",
        action="store_true",
        default=_env_bool("UNP_PIPELINE_GOV_REBUILD_ENABLED", False),
    )
    parser.add_argument(
        "--gov-rebuild-interval",
        type=float,
        default=_env_float(
            "UNP_PIPELINE_GOV_REBUILD_INTERVAL_SECONDS",
            86400.0,
        ),
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=_env_float("UNP_PIPELINE_RETRY_DELAY_SECONDS", 60.0),
    )
    parser.add_argument(
        "--include-joint-stock",
        action="store_true",
        default=_env_bool("UNP_PIPELINE_INCLUDE_JOINT_STOCK", False),
    )
    parser.add_argument(
        "--health-max-age",
        type=float,
        default=_env_float("UNP_PIPELINE_HEALTH_MAX_AGE_SECONDS", 600.0),
    )
    parser.add_argument(
        "--alert-interval",
        type=float,
        default=_env_float(
            "PARSER_ALERTS_PROGRESS_INTERVAL_SECONDS",
            float(settings.PARSER_ALERTS_PROGRESS_INTERVAL_SECONDS),
        ),
    )
    return parser


def main() -> int:
    args = build_argparser().parse_args()
    if args.health:
        return check_health(args.status_path, args.health_max_age)
    if args.status:
        return print_status(args.status_path, args.checkpoint_path)

    worker = UnpPipeline(args)
    signal.signal(signal.SIGTERM, worker.request_stop)
    signal.signal(signal.SIGINT, worker.request_stop)
    return worker.run()


if __name__ == "__main__":
    raise SystemExit(main())
