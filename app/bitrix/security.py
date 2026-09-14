"""Browser embedding and public-origin rules for the Bitrix application."""
import re
from urllib.parse import urlsplit

BITRIX_FRAME_ORIGINS = "https://*.bitrix24.by https://*.bitrix24.ru https://*.bitrix24.com https://*.bitrix24.kz"
BITRIX_FRAME_POLICY = f"frame-ancestors 'self' {BITRIX_FRAME_ORIGINS};"


def portal_domain(value: str | None) -> str:
    domain = (value or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.bitrix24\.(?:by|ru|com|kz)", domain):
        raise ValueError("Некорректный домен портала Битрикс24.")
    return domain


def application_origin(value: str | None) -> str:
    parsed = urlsplit((value or "").strip())
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.port not in (None, 443)):
        raise ValueError("APP_URL должен содержать публичный HTTPS-адрес приложения без пути и параметров.")
    return f"https://{parsed.hostname}"
