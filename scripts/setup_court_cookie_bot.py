"""One-time, local-to-server setup. Never print or accept token values in argv."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from court_cookie_bot import Config, Exporter, Telegram, atomic_private_write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True, type=int)
    parser.add_argument("--chat-id", required=True, type=int)
    args = parser.parse_args()
    target = Path("/home/user/egr-secrets/court-control.env")
    if target.exists() or target.is_symlink():
        raise RuntimeError("Existing configuration must be reviewed, not overwritten")
    # Only the two bot credentials are read, into host memory, never displayed.
    result = subprocess.run([
        "/usr/bin/docker", "exec", "egr_api", "python", "-c",
        "from app.core.config import settings; import json; "
        "print(json.dumps({'alerts': settings.ALERT_TELEGRAM_BOT_TOKEN, "
        "'search': settings.TELEGRAM_BOT_TOKEN, 'default_chat': settings.ALERT_TELEGRAM_CHAT_ID}))"
    ], check=True, capture_output=True, text=True, timeout=30)
    tokens = json.loads(result.stdout)
    token = (tokens.get("alerts") or "").strip()
    if not token or token == (tokens.get("search") or "").strip():
        raise RuntimeError("Alerts bot must be configured separately from search bot")
    os.environ.update({"COURT_CONTROL_BOT_TOKEN": token,
                       "COURT_CONTROL_USER_ID": str(args.user_id),
                       "COURT_CONTROL_CHAT_ID": str(args.chat_id),
                       "COURT_CONTROL_DEFAULT_ALERT_CHAT_ID": str(tokens.get("default_chat") or "")})
    config = Config.from_env()
    telegram = Telegram(config.token)
    if telegram.request("getWebhookInfo", {}).get("url"):
        raise RuntimeError("Webhook configured; do not start a polling controller")
    user_chat = telegram.request("getChat", {"chat_id": config.user_id})
    if user_chat.get("type") != "private" or user_chat.get("id") != config.user_id:
        raise RuntimeError("Authorized user must have a private chat with this bot")
    destination = telegram.request("getChat", {"chat_id": config.notify_chat_id})
    if destination.get("id") != config.notify_chat_id:
        raise RuntimeError("Notification destination mismatch")
    status = Exporter(config).status()
    # Filesystem identity and mount checks happen before writing configuration.
    cookie_stat = config.cookie.stat()
    if cookie_stat.st_uid != os.getuid() or cookie_stat.st_mode & 0o077:
        raise RuntimeError("Cookie owner or permissions require review")
    if config.cookie.parent.stat().st_mode & 0o022:
        raise RuntimeError("Cookie directory must not be writable by other users")
    atomic_private_write(target,
        "COURT_CONTROL_BOT_TOKEN=" + token + "\n"
        + "COURT_CONTROL_USER_ID=" + str(config.user_id) + "\n"
        + "COURT_CONTROL_CHAT_ID=" + str(config.notify_chat_id) + "\n"
        + ("COURT_CONTROL_DEFAULT_ALERT_CHAT_ID=" + str(config.default_alert_chat_id) + "\n"
           if config.default_alert_chat_id is not None else ""))
    print(json.dumps({"configured": True, "private_chat_verified": True,
                      "webhook_present": False, "exporter_status": status["state"]["Status"]}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Court setup stopped: check bot, private chat, mount and permissions; details suppressed")
        raise SystemExit(1)
