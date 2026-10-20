"""Linux host controller. No application/DB imports, no cookie values in logs.

Run as the owner of court.cookie. Configuration is local, never Telegram input.
Only the fixed existing exporter may be started; no shell commands from messages.
"""
from __future__ import annotations

import json
import html
import math
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urljoin, urlparse

MAX_COOKIE = 16384
PROMPT_INTERVAL = 300
AUTH_CHECK_INTERVAL = 3600
COURT_REQUEST_INTERVAL = 30
COURT_AUTH_CHECK_URL = "https://service.court.gov.by/ru/juridical/judgmentresults"
COOKIE_PROMPT = (
    "Пришлите полный Cookie обычным текстовым сообщением в этот личный чат — "
    "без команды и без файла. Нужны ASP.NET_SessionId и .ASPXAUTH. "
    "После сохранения бот продолжит остановленную выгрузку. "
    "Сообщение с кукой будет удалено по возможности."
)


class ControlError(Exception):
    """Fixed safe messages only. Never wrap an exception containing a token URL."""


class PollConflict(ControlError):
    pass


@dataclass(frozen=True)
class Config:
    token: str = field(repr=False)
    user_id: int
    notify_chat_id: int
    cookie: Path
    state: Path
    container: str = "egr_court_export"
    default_alert_chat_id: int | None = None

    @classmethod
    def from_env(cls):
        cfg = cls(
            token=os.environ["COURT_CONTROL_BOT_TOKEN"].strip(),
            user_id=int(os.environ["COURT_CONTROL_USER_ID"]),
            notify_chat_id=int(os.environ["COURT_CONTROL_CHAT_ID"]),
            cookie=Path(os.environ.get("COURT_CONTROL_COOKIE", "/home/user/egr-secrets/court.cookie")),
            state=Path(os.environ.get("COURT_CONTROL_STATE", "/home/user/egr-secrets/court-control-state.json")),
            default_alert_chat_id=(int(os.environ["COURT_CONTROL_DEFAULT_ALERT_CHAT_ID"])
                                   if os.environ.get("COURT_CONTROL_DEFAULT_ALERT_CHAT_ID") else None),
        )
        if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", cfg.token):
            raise ControlError("Invalid bot configuration")
        if cfg.user_id <= 0 or cfg.notify_chat_id == 0:
            raise ControlError("Explicit authorized user and destination chat are required")
        if cfg.default_alert_chat_id == 0 or cfg.default_alert_chat_id == cfg.notify_chat_id:
            raise ControlError("Ordinary alerts require a separate default destination")
        if (not cfg.cookie.is_absolute() or not cfg.state.is_absolute()
                or cfg.cookie == cfg.state or cfg.cookie.name != "court.cookie"):
            raise ControlError("Separate absolute cookie and state paths are required")
        return cfg


def atomic_private_write(path: Path, value: str):
    if path.is_symlink() or not path.parent.is_dir():
        raise ControlError("Unsafe or missing destination")
    fd, name = tempfile.mkstemp(prefix=".court-control-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.chmod(name, 0o600)
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        if os.name == "posix":
            parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def parse_cookie(value: str, *, require_auth: bool = True) -> str:
    if len(value.encode("utf-8")) > MAX_COOKIE:
        raise ControlError("Cookie too large")
    value = value.lstrip("\ufeff").strip()
    value = re.sub(r"^/cookie(?:@[A-Za-z0-9_]+)?\s+", "", value)
    value = re.sub(r"^cookie\s*:\s*", "", value, flags=re.I)
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if lines and lines[0].lower() == "cookie":
        lines.pop(0)
    if len(lines) != 1 or any(ord(c) < 32 or ord(c) > 126 for c in lines[0]):
        raise ControlError("Expected one Cookie header")
    jar = SimpleCookie()
    try:
        jar.load(lines[0])
    except Exception:
        raise ControlError("Invalid Cookie header") from None
    if require_auth and any(key not in jar or not jar[key].value for key in ("ASP.NET_SessionId", ".ASPXAUTH")):
        raise ControlError("Both session and authentication cookies are required")
    if not jar:
        raise ControlError("Invalid Cookie header")
    # Reject silently ignored fragments and response Set-Cookie attributes.
    parts = [part.strip() for part in lines[0].split(";") if part.strip()]
    if (len(parts) != len(jar) or any("=" not in part for part in parts)
            or {part.split("=", 1)[0].strip() for part in parts} != set(jar)):
        raise ControlError("Invalid Cookie header")
    return "; ".join(m.OutputString() for m in jar.values()) + "\n"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Telegram:
    def __init__(self, token):
        self.token = token
        self.opener = build_opener(NoRedirect())

    def request(self, method, data):
        try:
            request = Request("https://api.telegram.org/bot" + self.token + "/" + method,
                              data=json.dumps(data).encode(),
                              headers={"Content-Type": "application/json"})
            with self.opener.open(request, timeout=40) as response:
                result = json.loads(response.read(2_000_000))
            if not result.get("ok"):
                raise ControlError("Telegram rejected request")
            return result["result"]
        except HTTPError as error:
            if error.code == 409:
                raise PollConflict("Another update consumer is active; controller stopped") from None
            raise ControlError("Telegram request failed") from None
        except PollConflict:
            raise
        except Exception:
            raise ControlError("Telegram request failed") from None

    def cookie_document(self, document):
        if (not document.get("file_name", "").lower().endswith(".txt")
                or not 0 < document.get("file_size", 0) <= MAX_COOKIE):
            raise ControlError("Expected small UTF-8 txt file")
        info = self.request("getFile", {"file_id": document["file_id"]})
        path = info.get("file_path", "")
        if not re.fullmatch(r"[A-Za-z0-9_/-]+\.txt", path) or ".." in path:
            raise ControlError("Unexpected Telegram file path")
        try:
            with self.opener.open("https://api.telegram.org/file/bot" + self.token + "/" + path,
                                  timeout=20) as response:
                body = response.read(MAX_COOKIE + 1)
            if len(body) > MAX_COOKIE:
                raise ValueError()
            return body.decode("utf-8-sig")
        except Exception:
            raise ControlError("Cookie document could not be read") from None

    def send(self, chat, text):
        return self.request("sendMessage", {"chat_id": chat, "text": text,
                                            "protect_content": True})


def confirmed_auth_response(status, headers, body=""):
    """Recognized login only; never infer authentication failure from blank 200."""
    if status in (401, 403) or headers.get("REQUIRES_AUTH") == "1":
        return True
    def login_url(value):
        url = urlparse(urljoin(COURT_AUTH_CHECK_URL, html.unescape(value)))
        return (url.scheme == "https" and url.hostname == "service.court.gov.by"
                and url.path.lower().rstrip("/").endswith("/account/login"))
    if status in (301, 302, 303, 307, 308):
        return login_url(headers.get("Location", ""))
    return status == 200 and any(login_url(action) for action in re.findall(
        r"<form\b[^>]*\baction\s*=\s*['\"]([^'\"]+)", body, re.I))


class CourtAuthProbe:
    """One read, no redirects/retries, no cookie renewal or export state writes."""
    def __init__(self, config):
        self.config = config
        self.opener = build_opener(NoRedirect())

    def check(self, now):
        rate = self.config.cookie.parent / ".court-request-rate.txt"
        if rate.is_symlink() or self.config.cookie.is_symlink():
            raise ControlError("Unsafe court diagnostic path")
        if rate.exists():
            last = float(rate.read_text(encoding="ascii").strip())
            if not math.isfinite(last) or last < 0:
                raise ControlError("Invalid court request timestamp")
            if now < last + COURT_REQUEST_INTERVAL:
                return {"status": "deferred", "retry_at": last + COURT_REQUEST_INTERVAL}
        # An older file may contain only a session cookie. Let the site confirm
        # authentication failure; submissions still require both cookie pairs.
        cookie = parse_cookie(self.config.cookie.read_text(encoding="utf-8-sig"), require_auth=False).strip()
        atomic_private_write(rate, f"{now:.6f}\n")
        request = Request(COURT_AUTH_CHECK_URL,
                          headers={"Cookie": cookie, "User-Agent": "Mozilla/5.0",
                                   "Referer": COURT_AUTH_CHECK_URL})
        try:
            with self.opener.open(request, timeout=8) as response:
                status, headers = response.status, response.headers
                body = response.read(65536).decode("utf-8", errors="replace")
        except HTTPError as error:
            status, headers, body = error.code, error.headers, ""
            error.close()
        except Exception:
            raise ControlError("Court diagnostic unavailable") from None
        return {"status": "auth_required" if confirmed_auth_response(status, headers, body)
                else "not_confirmed"}


class Exporter:
    def __init__(self, config):
        self.config = config

    def _run(self, *args, include_stderr=False):
        try:
            result = subprocess.run(["/usr/bin/docker", *args], check=True,
                                    capture_output=True, text=True, timeout=25)
            return result.stdout + (result.stderr if include_stderr else "")
        except Exception:
            raise ControlError("Docker command failed") from None

    def status(self):
        # Do not read container Env, logs, command arguments or cookie contents.
        result = json.loads(self._run("inspect", "--format",
            '{"id":{{json .Id}},"state":{{json .State}},"mounts":{{json .Mounts}}}',
            self.config.container))
        expected = str(self.config.cookie.parent.resolve())
        if not any(m.get("Type") == "bind" and m.get("Source") == expected
                   and m.get("Destination") == "/court-secrets" for m in result["mounts"]):
            raise ControlError("Exporter cookie mount does not match configuration")
        return result

    def start(self, container_id):
        # Pin the inspected container ID, never create another exporter.
        self._run("start", container_id)

    def ordinary_alert_delivered(self, status):
        logs = self._run("logs", "--since", status["state"]["StartedAt"],
                         "--tail", "50", self.config.container, include_stderr=True)
        return "Court Telegram notification: sent" in logs.splitlines()

    def stop_report(self, status):
        # Read only this run, into memory. Never print logs or exception text.
        logs = self._run("logs", "--since", status["state"]["StartedAt"],
                         "--tail", "50", self.config.container, include_stderr=True)
        lines = logs.splitlines()
        for line in reversed(lines):
            try:
                item = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(item, dict) and item.get("reason") in {
                "blank_response", "unrecognized_response", "unexpected_redirect",
            }:
                progress = next((re.search(r"court=(\d+); page=(\d+)", entry)
                                 for entry in reversed(lines) if "Court export stopped:" in entry), None)
                if all(isinstance(item.get(key), int) for key in ("court_id", "type_proc", "page")):
                    progress_key = ":".join(str(item[key]) for key in ("court_id", "type_proc", "page"))
                else:
                    progress_key = ":".join(progress.groups()) if progress else "unknown"
                return {"reason": item["reason"],
                        "progress": progress_key}
        if status["state"].get("ExitCode") == 2 and any(
            line.startswith(("Court session expired;", "Court access denied;")) for line in lines
        ):
            return {"reason": "auth_required", "progress": "unknown"}
        return {"reason": "unknown", "progress": "unknown"}


class Controller:
    def __init__(self, config, telegram, exporter, clock=time.time, auth_probe=None):
        self.config, self.telegram, self.exporter, self.clock = config, telegram, exporter, clock
        self.state = json.loads(config.state.read_text()) if config.state.exists() else {}
        self.offset = int(self.state.get("offset", 0))
        self.auth_probe = auth_probe if auth_probe is not None else CourtAuthProbe(config)

    def save(self):
        atomic_private_write(self.config.state, json.dumps(self.state))

    def authorized(self, message):
        return (message.get("chat", {}).get("type") == "private"
                and message.get("chat", {}).get("id") == self.config.user_id
                and message.get("from", {}).get("id") == self.config.user_id
                and not message.get("from", {}).get("is_bot", False)
                and not any(message.get(key) for key in
                    ("forward_origin", "forward_date", "sender_chat", "via_bot", "edit_date")))

    def send_prompt(self):
        last_prompt = self.state.get("last_cookie_prompt_at")
        if last_prompt is not None and 0 <= self.clock() - last_prompt < PROMPT_INTERVAL:
            return
        self.telegram.send(self.config.user_id, COOKIE_PROMPT)
        self.state["last_cookie_prompt_at"] = self.clock()
        self.save()

    def handle(self, update):
        update_id = update["update_id"]
        if update_id < self.offset:
            return
        # Claim before mutations: after a crash do not apply the same cookie or
        # restart twice. A crash in this tiny window requires resending the cookie.
        self.state["offset"] = update_id + 1
        self.save()
        self.offset = update_id + 1
        message = update.get("message", {})
        if not self.authorized(message):
            return
        text = message.get("text", "").strip()
        if text in {"/start", "/help"}:
            self.send_prompt()
            return
        if text == "/status":
            status = self.exporter.status()
            if status["state"].get("Status") == "running":
                reply = "Выгрузка судов работает."
            elif self.state.get("retry_due") is not None:
                minutes = max(0, int((self.state["retry_due"] - self.clock() + 59) // 60))
                reply = f"Сайт вернул пустой ответ. Повтор той же страницы запланирован через {minutes} мин."
            elif (self.exporter.stop_report(status)["reason"] == "auth_required"
                  or self.state.get("auth_confirmed_stop") == status["id"] + ":" + status["state"]["FinishedAt"]):
                reply = "Сайт отклонил авторизацию. Выгрузка ждёт свежую куку."
            else:
                reply = "Выгрузка остановлена; требуется диагностика ответа сайта или сохранения данных."
            self.telegram.send(self.config.user_id, reply)
            return
        if "document" not in message and not any(
            marker in text.lower() for marker in ("cookie", "asp.net_sessionid", ".aspxauth", "=")
        ):
            # Ordinary conversation is neither a credential nor something to delete.
            return
        reply = "Не удалось обновить куку. Файл/запуск нужно проверить; пришлите куку повторно после проверки."
        stage = "format"
        try:
            if not 0 <= self.clock() - message.get("date", 0) <= 600:
                raise ControlError("Old message rejected")
            cookie = parse_cookie(self.telegram.cookie_document(message["document"])
                                  if "document" in message else text)
            stage = "exporter"
            status = self.exporter.status()
            if status["state"].get("Status") not in {"exited", "created"}:
                reply = "Выгрузка ещё работает или останавливается. Кука не изменена; повторите после остановки."
            else:
                atomic_private_write(self.config.cookie, cookie)
                self.exporter.start(status["id"])
                self.state["retry_due"] = None
                self.state["auth_confirmed_stop"] = None
                self.save()
                reply = ("Кука сохранена, существующий контейнер запущен с прежним прогрессом. "
                         "Авторизация проверится при следующем запросе с разрешённой паузой. "
                         "Это ещё не подтверждение успешной выгрузки.")
        except Exception:
            # Neither exception text nor incoming message is ever logged.
            if stage == "format":
                reply = ("Кука не сохранена. Пришлите свежий полный Cookie одним текстовым сообщением: "
                         "ASP.NET_SessionId=…; .ASPXAUTH=… (вместо многоточий — настоящие значения). "
                         "Остальные пары Cookie можно оставить. Секреты сюда бот не повторяет.")
        finally:
            try:
                self.telegram.request("deleteMessage", {"chat_id": self.config.user_id,
                                                        "message_id": message["message_id"]})
            except Exception:
                reply += " Не удалось удалить сообщение с кукой — удалите его вручную."
        self.telegram.send(self.config.user_id, reply)

    def notify_auth_required(self, marker):
        if self.state.get("notified_stop") == marker:
            return
        receipt = self.telegram.send(self.config.notify_chat_id,
            "⚠️ Сайт судов отклонил авторизацию. Выгрузка ждёт обновления сессии. "
            "Пришлите свежий полный Cookie обычным текстом в личный чат этому боту. "
            "Он сохранит куку и продолжит с прежнего места.")
        if (isinstance(receipt, dict) and isinstance(receipt.get("chat"), dict)
                and receipt["chat"].get("id") != self.config.notify_chat_id):
            raise ControlError("Unexpected notification destination in receipt")
        self.state["notified_stop"] = marker
        if isinstance(receipt, dict) and isinstance(receipt.get("message_id"), int):
            self.state["auth_notification_message_id"] = receipt["message_id"]
            self.state["auth_notification_chat_id"] = self.config.notify_chat_id
        if self.config.notify_chat_id == self.config.user_id:
            self.state["last_cookie_prompt_at"] = self.clock()
        self.save()

    def check_stopped_auth(self, status, marker):
        if self.state.get("notified_stop") == marker:
            return
        generation = [self.config.cookie.stat().st_mtime_ns, self.config.cookie.stat().st_size]
        if (self.state.get("auth_confirmed_stop") == marker
                and self.state.get("auth_cookie_generation") == generation):
            self.notify_auth_required(marker)
            return
        if (self.state.get("auth_probe_stop") == marker
                and self.clock() < self.state.get("next_auth_probe_at", 0)):
            return
        # Persist the cooldown before HTTP: a controller crash cannot flood the site.
        self.state.update(auth_probe_stop=marker, next_auth_probe_at=self.clock() + AUTH_CHECK_INTERVAL)
        self.save()
        try:
            result = self.auth_probe.check(self.clock())
        except Exception:
            print("Court stopped-session diagnostic unavailable; details suppressed", flush=True)
            return
        if result.get("status") == "deferred":
            self.state["next_auth_probe_at"] = result["retry_at"]
            self.save()
            return
        if result.get("status") != "auth_required":
            return
        current = self.exporter.status()
        current_generation = [self.config.cookie.stat().st_mtime_ns, self.config.cookie.stat().st_size]
        if (current["state"].get("Status") != "exited"
                or current["id"] + ":" + current["state"]["FinishedAt"] != marker
                or current_generation != generation):
            return
        self.state.update(auth_confirmed_stop=marker, auth_cookie_generation=generation,
                          retry_due=None)
        self.save()
        self.notify_auth_required(marker)

    def check_stop(self):
        status = self.exporter.status()
        state = status["state"]
        if state.get("Status") != "exited":
            return
        marker = status["id"] + ":" + state["FinishedAt"]
        if self.state.get("handled_stop") != marker:
            report = self.exporter.stop_report(status) if state.get("ExitCode") else {"reason": "complete"}
            if (report["reason"] not in {"auth_required", "complete"}
                    and self.config.default_alert_chat_id is not None
                    and self.state.get("ordinary_notified_stop") != marker):
                # Covers the already-running old exporter and failed deliveries.
                # Never duplicate a successfully delivered ordinary export alert.
                if not self.exporter.ordinary_alert_delivered(status):
                    reasons = {
                        "blank_response": "Пустой ответ сайта после повторных попыток.",
                        "unrecognized_response": "Нераспознанный ответ сайта.",
                        "unexpected_redirect": "Неожиданное перенаправление сайта.",
                    }
                    self.telegram.send(self.config.default_alert_chat_id,
                        "❌ Выгрузка судов остановлена: ошибка ответа, сети или сохранения.\n"
                        + reasons.get(report["reason"], "Требуется диагностика ошибки выгрузки.")
                        + "\nПозиция (суд:тип:страница): " + report.get("progress", "unknown")
                        + "\nПрогресс сохранён. Это не подтверждённая ошибка авторизации.")
                self.state["ordinary_notified_stop"] = marker
            self.state["retry_due"] = None
            if report["reason"] == "auth_required":
                # Exit code alone is insufficient: argparse also exits 2.
                self.notify_auth_required(marker)
            elif report["reason"] == "blank_response":
                progress = report["progress"]
                failures = (self.state.get("blank_failures", 0) + 1
                            if self.state.get("blank_progress") == progress else 1)
                failures = min(failures, 4)
                delay = min(3600, 600 * 2 ** (failures - 1))
                try:
                    finished = datetime.fromisoformat(state["FinishedAt"].replace("Z", "+00:00")).timestamp()
                    if not 0 <= self.clock() - finished <= 7 * 86400:
                        finished = self.clock()
                except (TypeError, ValueError):
                    finished = self.clock()
                self.state.update(blank_progress=progress, blank_failures=failures,
                                  retry_due=finished + delay)
                print(f"Court blank response: resume scheduled in {delay} seconds", flush=True)
            else:
                print("Court exporter stopped; no cookie request (reason=" + report["reason"] + ")", flush=True)
            self.state["handled_stop"] = marker
            self.state["handled_reason"] = report["reason"]
            self.save()
        due = self.state.get("retry_due")
        if due is not None and self.clock() >= due:
            # Inspection above confirms it is still the same stopped run.
            self.exporter.start(status["id"])
            self.state["retry_due"] = None
            self.save()
            print("Court exporter resumed after blank-response cooldown", flush=True)
            return
        if due is None:
            reason = self.state.get("handled_reason") or self.exporter.stop_report(status)["reason"]
            if reason not in {"complete", "auth_required"}:
                self.check_stopped_auth(status, marker)

    def heartbeat(self):
        # Let the exporter fall back to its auth alert if this controller dies.
        atomic_private_write(self.config.cookie.parent / ".court-control-heartbeat.json",
                             json.dumps({"updated_at": self.clock(),
                                         "auth_chat_id": self.config.notify_chat_id}))


def main():
    import fcntl  # Linux host only. Do not mount Docker socket into the API.
    import signal
    stopping = False

    def request_stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    config = Config.from_env()
    os.umask(0o077)
    with config.state.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        telegram = Telegram(config.token)
        if telegram.request("getWebhookInfo", {}).get("url"):
            raise PollConflict("Webhook configured; nothing changed")
        controller = Controller(config, telegram, Exporter(config))
        while not stopping:
            try:
                controller.heartbeat()
                try:
                    controller.check_stop()
                except Exception:
                    # A missing notification destination must not prevent the
                    # authorized private chat from renewing the cookie.
                    print("Court stop notification unavailable; details suppressed", flush=True)
                updates = telegram.request("getUpdates", {"offset": controller.offset,
                    "timeout": 25, "allowed_updates": ["message"], "limit": 20})
                for update in updates:
                    if stopping:
                        break
                    controller.handle(update)
            except PollConflict:
                raise
            except Exception:
                print("Court controller temporarily unavailable; details suppressed", flush=True)
                time.sleep(15)


if __name__ == "__main__":
    try:
        main()
    except PollConflict:
        print("Court controller stopped: another Telegram consumer or webhook exists", flush=True)
        raise SystemExit(78)
    except Exception:
        print("Court controller stopped; check local configuration and permissions", flush=True)
        raise SystemExit(1)
