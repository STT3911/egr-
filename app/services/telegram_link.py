"""One-time Telegram account linking and bot-account merging."""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from uuid import UUID

import redis
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import CompanySubscription, SubscriptionEvent, User


LINK_TTL_SECONDS = 15 * 60
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,128}$")
_TOKEN_PREFIX = "telegram-link:token:"
_USER_PREFIX = "telegram-link:user:"


class TelegramLinkError(RuntimeError):
    pass


class TelegramLinkUnavailable(TelegramLinkError):
    pass


class TelegramAlreadyLinked(TelegramLinkError):
    pass


@dataclass(frozen=True)
class TelegramLinkResult:
    user_id: str
    subscriptions_moved: int
    events_moved: int


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
    )


def create_telegram_link(user_id: str) -> str:
    token = secrets.token_urlsafe(24)
    digest = _token_digest(token)
    token_key = f"{_TOKEN_PREFIX}{digest}"
    user_key = f"{_USER_PREFIX}{user_id}"
    client = _redis_client()
    try:
        previous_digest = client.get(user_key)
        pipeline = client.pipeline()
        if previous_digest:
            pipeline.delete(f"{_TOKEN_PREFIX}{previous_digest}")
        pipeline.setex(token_key, LINK_TTL_SECONDS, user_id)
        pipeline.setex(user_key, LINK_TTL_SECONDS, digest)
        pipeline.execute()
        return token
    except redis.RedisError as exc:
        raise TelegramLinkUnavailable(
            "Сервис одноразовой привязки временно недоступен"
        ) from exc
    finally:
        client.close()


def consume_telegram_link(token: str) -> str | None:
    if not _TOKEN_RE.fullmatch(token):
        return None

    digest = _token_digest(token)
    token_key = f"{_TOKEN_PREFIX}{digest}"
    client = _redis_client()
    try:
        user_id = client.execute_command("GETDEL", token_key)
        if user_id:
            user_key = f"{_USER_PREFIX}{user_id}"
            if client.get(user_key) == digest:
                client.delete(user_key)
        return user_id
    except redis.RedisError as exc:
        raise TelegramLinkUnavailable(
            "Сервис одноразовой привязки временно недоступен"
        ) from exc
    finally:
        client.close()


def revoke_telegram_links(user_id: str) -> None:
    client = _redis_client()
    try:
        user_key = f"{_USER_PREFIX}{user_id}"
        digest = client.get(user_key)
        pipeline = client.pipeline()
        pipeline.delete(user_key)
        if digest:
            pipeline.delete(f"{_TOKEN_PREFIX}{digest}")
        pipeline.execute()
    except redis.RedisError as exc:
        raise TelegramLinkUnavailable(
            "Сервис одноразовой привязки временно недоступен"
        ) from exc
    finally:
        client.close()


def _merge_event_types(first: list[str] | None, second: list[str] | None) -> list[str]:
    first_types = first or []
    second_types = second or []
    if not first_types or not second_types:
        return []
    return sorted(set(first_types) | set(second_types))


def link_telegram_user(
    db: Session,
    *,
    target_user_id: str,
    telegram_id: int,
) -> TelegramLinkResult:
    target_user = db.get(User, UUID(target_user_id))
    if not target_user or not target_user.is_active:
        raise TelegramLinkError("Аккаунт для привязки не найден")
    if target_user.telegram_id == telegram_id:
        return TelegramLinkResult(str(target_user.id), 0, 0)
    if target_user.telegram_id is not None:
        raise TelegramAlreadyLinked(
            "К этому аккаунту уже привязан другой Telegram"
        )

    telegram_user = (
        db.query(User)
        .filter(User.telegram_id == telegram_id)
        .first()
    )
    subscriptions_moved = 0
    events_moved = 0

    if telegram_user and telegram_user.id != target_user.id:
        if telegram_user.email or telegram_user.password_hash:
            raise TelegramAlreadyLinked(
                "Этот Telegram уже привязан к другому аккаунту"
            )

        source_subscriptions = (
            db.query(CompanySubscription)
            .filter(CompanySubscription.user_id == telegram_user.id)
            .all()
        )
        for source_subscription in source_subscriptions:
            target_subscription = (
                db.query(CompanySubscription)
                .filter(
                    CompanySubscription.user_id == target_user.id,
                    CompanySubscription.unp == source_subscription.unp,
                )
                .first()
            )
            if target_subscription:
                target_subscription.event_types = _merge_event_types(
                    target_subscription.event_types,
                    source_subscription.event_types,
                )
                db.delete(source_subscription)
            else:
                source_subscription.user_id = target_user.id
                subscriptions_moved += 1

        db.flush()
        events_moved = (
            db.query(SubscriptionEvent)
            .filter(SubscriptionEvent.user_id == telegram_user.id)
            .update(
                {SubscriptionEvent.user_id: target_user.id},
                synchronize_session=False,
            )
        )
        db.query(User).filter(User.id == telegram_user.id).delete(
            synchronize_session=False
        )
        db.flush()

    target_user.telegram_id = telegram_id
    return TelegramLinkResult(
        str(target_user.id),
        subscriptions_moved,
        int(events_moved or 0),
    )
