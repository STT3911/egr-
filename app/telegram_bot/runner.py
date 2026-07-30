"""Long polling Telegram bot for EGR company search."""
from __future__ import annotations

import asyncio
import logging
import re
from html import escape
from typing import Any

import httpx

from app.core.database import SessionLocal
from app.database.models import User, CompanySubscription
from app.services.telegram_link import (
    TelegramAlreadyLinked,
    TelegramLinkError,
    TelegramLinkUnavailable,
    consume_telegram_link,
    link_telegram_user,
)
from app.telegram_bot.formatting import (
    HELP_TEXT,
    company_keyboard,
    format_company_card,
    format_detailed_company_report,
    format_lookup_message,
    lookup_keyboard,
)

logger = logging.getLogger("egr_aggregator.telegram_bot")
UNP_RE = re.compile(r"^\d{9}$")


class EGRApiClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 10.0,
    ):
        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key

        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def lookup(self, query: str, limit: int) -> list[dict[str, Any]]:
        response = await self._client.get(
            "/api/v1/companies/lookup",
            params={"q": query, "limit": limit},
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("results") or []

    async def get_company(self, unp: str) -> dict[str, Any]:
        response = await self._client.get(
            f"/api/v1/companies/{unp}",
            params={"db_only": "true"},
        )
        response.raise_for_status()
        return response.json()

    async def _get_optional(self, path: str, **params: Any) -> dict[str, Any] | None:
        response = await self._client.get(path, params=params or None)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def get_detailed_report(self, unp: str) -> dict[str, Any]:
        profile = await self.get_company(unp)
        requests = {
            "grp": self._get_optional(f"/api/v1/grp/{unp}"),
            "bankruptcy": self._get_optional(f"/api/v1/companies/{unp}/bankruptcy"),
            "tax_debt": self._get_optional(
                f"/api/v1/companies/{unp}/tax-debt",
                limit=100,
            ),
            "risk": self._get_optional(f"/api/v1/companies/{unp}/risk"),
            "related": self._get_optional(
                f"/api/v1/companies/{unp}/related",
                limit=50,
            ),
        }
        results = await asyncio.gather(*requests.values(), return_exceptions=True)
        report: dict[str, Any] = {"profile": profile, "errors": {}}
        for source, result in zip(requests, results):
            if isinstance(result, Exception):
                if isinstance(result, httpx.HTTPStatusError):
                    detail = f"HTTP {result.response.status_code}"
                else:
                    detail = result.__class__.__name__
                report["errors"][source] = detail
                logger.warning("Detailed report source failed: unp=%s source=%s error=%s", unp, source, result)
                continue
            report[source] = result
        return report


class TelegramApiClient:
    def __init__(self, token: str, timeout_seconds: float = 10.0):
        self._base_url = f"https://api.telegram.org/bot{token}"
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def close(self) -> None:
        await self._client.aclose()

    async def get_updates(self, offset: int | None, timeout: int) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset

        response = await self._client.post(f"{self._base_url}/getUpdates", json=payload)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram getUpdates failed: {data}")
        return data.get("result") or []

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text[:4096],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        response = await self._client.post(f"{self._base_url}/sendMessage", json=payload)
        response.raise_for_status()

    async def answer_callback_query(self, callback_query_id: str) -> None:
        response = await self._client.post(
            f"{self._base_url}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id},
        )
        response.raise_for_status()


class TelegramBot:
    def __init__(
        self,
        telegram: TelegramApiClient,
        egr: EGRApiClient,
        lookup_limit: int = 5,
    ):
        self.telegram = telegram
        self.egr = egr
        self.lookup_limit = lookup_limit

    async def process_update(self, update: dict[str, Any]) -> None:
        if "callback_query" in update:
            await self._handle_callback(update["callback_query"])
            return

        message = update.get("message")
        if message:
            await self._handle_message(message)

    async def _handle_message(self, message: dict[str, Any]) -> None:
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        sender = message.get("from") or {}
        telegram_id: int | None = sender.get("id")
        text = (message.get("text") or "").strip()
        if chat_id is None:
            return

        lower = text.lower()
        command = lower.split(maxsplit=1)[0].split("@", 1)[0] if lower else ""
        if command == "/start":
            parts = text.split(maxsplit=1)
            argument = parts[1].strip() if len(parts) > 1 else ""
            if argument.startswith("link_"):
                await self._handle_link_account(
                    chat_id,
                    telegram_id,
                    argument.removeprefix("link_"),
                )
            else:
                await self.telegram.send_message(chat_id, HELP_TEXT)
            return
        if command == "/help":
            await self.telegram.send_message(chat_id, HELP_TEXT)
            return

        if command == "/more":
            parts = text.split(maxsplit=1)
            unp_str = parts[1].strip() if len(parts) > 1 else ""
            if not UNP_RE.fullmatch(unp_str):
                reply_text = ((message.get("reply_to_message") or {}).get("text") or "").strip()
                match = re.search(r"(?<!\d)(\d{9})(?!\d)", reply_text)
                unp_str = match.group(1) if match else ""
            await self._handle_more(chat_id, unp_str)
            return

        if lower.startswith("/subscribe") or lower.startswith("/sub "):
            parts = text.split(maxsplit=1)
            unp_str = parts[1].strip() if len(parts) > 1 else ""
            await self._handle_subscribe(chat_id, telegram_id, unp_str)
            return

        if lower.startswith("/unsubscribe") or lower.startswith("/unsub "):
            parts = text.split(maxsplit=1)
            unp_str = parts[1].strip() if len(parts) > 1 else ""
            await self._handle_unsubscribe(chat_id, telegram_id, unp_str)
            return

        if lower == "/mysubs":
            await self._handle_mysubs(chat_id, telegram_id)
            return

        if not text or len(text) < 2:
            await self.telegram.send_message(chat_id, HELP_TEXT)
            return

        if UNP_RE.fullmatch(text):
            await self._send_company_card(chat_id, text)
            return

        await self._send_lookup(chat_id, text)

    async def _handle_link_account(
        self,
        chat_id: int,
        telegram_id: int | None,
        token: str,
    ) -> None:
        if not telegram_id:
            await self.telegram.send_message(
                chat_id,
                "Не удалось определить ваш Telegram ID.",
            )
            return

        try:
            target_user_id = consume_telegram_link(token)
        except TelegramLinkUnavailable:
            await self.telegram.send_message(
                chat_id,
                "Сервис привязки временно недоступен. Создайте новую ссылку на сайте позже.",
            )
            return
        if not target_user_id:
            await self.telegram.send_message(
                chat_id,
                "Ссылка недействительна или уже истекла. Создайте новую в центре событий.",
            )
            return

        db = SessionLocal()
        try:
            result = link_telegram_user(
                db,
                target_user_id=target_user_id,
                telegram_id=telegram_id,
            )
            db.commit()
            details = ""
            if result.subscriptions_moved:
                details = (
                    f"\nПеренесено подписок из бота: {result.subscriptions_moved}."
                )
            await self.telegram.send_message(
                chat_id,
                "✅ <b>Telegram подключён к аккаунту TENDEX.</b>\n"
                "Теперь изменения по веб-подпискам будут приходить сюда."
                f"{details}",
            )
        except TelegramAlreadyLinked as exc:
            db.rollback()
            await self.telegram.send_message(chat_id, escape(str(exc)))
        except TelegramLinkError:
            db.rollback()
            await self.telegram.send_message(
                chat_id,
                "Не удалось привязать аккаунт. Создайте новую ссылку на сайте.",
            )
        except Exception as exc:
            db.rollback()
            logger.exception(
                "Telegram account link failed telegram_id=%s: %s",
                telegram_id,
                exc,
            )
            await self.telegram.send_message(
                chat_id,
                "Ошибка при привязке аккаунта. Попробуйте ещё раз позже.",
            )
        finally:
            db.close()

    async def _handle_subscribe(self, chat_id: int, telegram_id: int | None, unp_str: str) -> None:
        if not telegram_id:
            await self.telegram.send_message(chat_id, "Не удалось определить ваш Telegram ID.")
            return
        if not UNP_RE.fullmatch(unp_str):
            await self.telegram.send_message(
                chat_id, "Укажите УНП (9 цифр):\n<code>/subscribe 193712492</code>"
            )
            return

        unp = int(unp_str)
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                user = User(telegram_id=telegram_id, is_active=True)
                db.add(user)
                db.flush()

            sub = (
                db.query(CompanySubscription)
                .filter(CompanySubscription.user_id == user.id, CompanySubscription.unp == unp)
                .first()
            )
            if sub:
                await self.telegram.send_message(
                    chat_id, f"Вы уже подписаны на УНП <code>{escape(unp_str)}</code>."
                )
                return

            db.add(CompanySubscription(user_id=user.id, unp=unp, event_types=[], source="telegram"))
            db.commit()
            await self.telegram.send_message(
                chat_id,
                f"✅ Подписка на УНП <code>{escape(unp_str)}</code> оформлена.\n"
                "Вы получите уведомление при изменениях по всем доступным источникам.",
            )
        except Exception as exc:
            db.rollback()
            logger.exception("Subscribe error telegram_id=%s unp=%s: %s", telegram_id, unp_str, exc)
            await self.telegram.send_message(chat_id, "Ошибка при оформлении подписки. Попробуйте позже.")
        finally:
            db.close()

    async def _handle_unsubscribe(self, chat_id: int, telegram_id: int | None, unp_str: str) -> None:
        if not telegram_id:
            await self.telegram.send_message(chat_id, "Не удалось определить ваш Telegram ID.")
            return
        if not UNP_RE.fullmatch(unp_str):
            await self.telegram.send_message(
                chat_id, "Укажите УНП (9 цифр):\n<code>/unsubscribe 193712492</code>"
            )
            return

        unp = int(unp_str)
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                await self.telegram.send_message(chat_id, "У вас нет активных подписок.")
                return

            sub = (
                db.query(CompanySubscription)
                .filter(CompanySubscription.user_id == user.id, CompanySubscription.unp == unp)
                .first()
            )
            if not sub:
                await self.telegram.send_message(
                    chat_id, f"Подписка на УНП <code>{escape(unp_str)}</code> не найдена."
                )
                return

            db.delete(sub)
            db.commit()
            await self.telegram.send_message(
                chat_id, f"❌ Подписка на УНП <code>{escape(unp_str)}</code> отменена."
            )
        except Exception as exc:
            db.rollback()
            logger.exception("Unsubscribe error telegram_id=%s unp=%s: %s", telegram_id, unp_str, exc)
            await self.telegram.send_message(chat_id, "Ошибка при отмене подписки. Попробуйте позже.")
        finally:
            db.close()

    async def _handle_mysubs(self, chat_id: int, telegram_id: int | None) -> None:
        if not telegram_id:
            await self.telegram.send_message(chat_id, "Не удалось определить ваш Telegram ID.")
            return

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                await self.telegram.send_message(chat_id, "У вас нет активных подписок.")
                return

            subs = (
                db.query(CompanySubscription)
                .filter(CompanySubscription.user_id == user.id)
                .order_by(CompanySubscription.created_at.desc())
                .all()
            )
            if not subs:
                await self.telegram.send_message(chat_id, "У вас нет активных подписок.")
                return

            lines = [f"<b>Ваши подписки ({len(subs)}):</b>"]
            for s in subs:
                types = ", ".join(s.event_types) if s.event_types else "все события"
                lines.append(f"• УНП <code>{s.unp}</code> — {escape(types)}")
            lines.append("\nОтменить: <code>/unsubscribe 123456789</code>")
            await self.telegram.send_message(chat_id, "\n".join(lines))
        except Exception as exc:
            logger.exception("Mysubs error telegram_id=%s: %s", telegram_id, exc)
            await self.telegram.send_message(chat_id, "Ошибка при получении подписок.")
        finally:
            db.close()

    async def _handle_callback(self, callback_query: dict[str, Any]) -> None:
        callback_id = callback_query.get("id")
        if callback_id:
            await self.telegram.answer_callback_query(callback_id)

        data = callback_query.get("data") or ""
        message = callback_query.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return

        if data.startswith("company:"):
            unp = data.removeprefix("company:").strip()
            if UNP_RE.fullmatch(unp):
                await self._send_company_card(chat_id, unp)
                return

        await self.telegram.send_message(chat_id, HELP_TEXT)

    async def _send_lookup(self, chat_id: int, query: str) -> None:
        try:
            results = await self.egr.lookup(query, self.lookup_limit)
        except httpx.HTTPStatusError as exc:
            logger.warning(f"Lookup request failed: {exc.response.status_code}")
            await self.telegram.send_message(chat_id, "Не удалось выполнить поиск.")
            return
        except httpx.HTTPError as exc:
            logger.warning(f"Lookup request error: {exc}")
            await self.telegram.send_message(chat_id, "Сервис поиска временно недоступен.")
            return

        await self.telegram.send_message(
            chat_id,
            format_lookup_message(query, results),
            reply_markup=lookup_keyboard(results),
        )

    async def _send_company_card(self, chat_id: int, unp: str) -> None:
        try:
            company = await self.egr.get_company(unp)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                await self.telegram.send_message(
                    chat_id,
                    f"Компания с УНП {unp} не найдена.",
                )
                return
            logger.warning(
                "Company request failed: %s %s",
                exc.response.status_code,
                exc.response.text[:500],
            )
            await self.telegram.send_message(chat_id, "Не удалось получить карточку.")
            return
        except httpx.HTTPError as exc:
            logger.warning(f"Company request error: {exc}")
            await self.telegram.send_message(chat_id, "Сервис карточек временно недоступен.")
            return

        await self.telegram.send_message(
            chat_id,
            format_company_card(company),
            reply_markup=company_keyboard(unp),
        )

    async def _handle_more(self, chat_id: int, unp: str) -> None:
        if not UNP_RE.fullmatch(unp):
            await self.telegram.send_message(
                chat_id,
                "Укажите УНП: <code>/more 193712492</code>\n"
                "Или ответьте командой <code>/more</code> на сообщение, где есть УНП.",
            )
            return

        await self.telegram.send_message(
            chat_id,
            f"⏳ Собираю подробный отчёт по УНП <code>{escape(unp)}</code> из всех источников…",
        )
        try:
            report = await self.egr.get_detailed_report(unp)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                await self.telegram.send_message(chat_id, f"Компания с УНП {escape(unp)} не найдена.")
                return
            logger.warning("Detailed company report failed: %s %s", exc.response.status_code, exc.response.text[:500])
            await self.telegram.send_message(chat_id, "Не удалось получить подробный отчёт.")
            return
        except httpx.HTTPError as exc:
            logger.warning("Detailed company report request error: %s", exc)
            await self.telegram.send_message(chat_id, "Сервис подробных отчётов временно недоступен.")
            return

        for message_text in format_detailed_company_report(report):
            await self.telegram.send_message(chat_id, message_text)


async def run_polling() -> None:
    from app.core.config import settings

    if not settings.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run the Telegram bot")

    telegram_timeout = max(
        settings.TELEGRAM_HTTP_TIMEOUT_SECONDS,
        settings.TELEGRAM_POLL_TIMEOUT_SECONDS + 5,
    )
    telegram = TelegramApiClient(
        settings.TELEGRAM_BOT_TOKEN,
        timeout_seconds=telegram_timeout,
    )
    egr = EGRApiClient(
        settings.TELEGRAM_API_BASE_URL,
        api_key=settings.TELEGRAM_API_KEY,
        timeout_seconds=settings.TELEGRAM_HTTP_TIMEOUT_SECONDS,
    )
    bot = TelegramBot(
        telegram=telegram,
        egr=egr,
        lookup_limit=settings.TELEGRAM_LOOKUP_LIMIT,
    )
    offset: int | None = None

    logger.info("Telegram bot started")
    try:
        while True:
            try:
                updates = await telegram.get_updates(
                    offset=offset,
                    timeout=settings.TELEGRAM_POLL_TIMEOUT_SECONDS,
                )
                for update in updates:
                    update_id = update.get("update_id")
                    if isinstance(update_id, int):
                        offset = update_id + 1
                    try:
                        await bot.process_update(update)
                    except Exception as exc:
                        logger.exception(f"Failed to process Telegram update: {exc}")
            except Exception as exc:
                logger.warning(f"Telegram polling error: {exc}")
                await asyncio.sleep(5)
    finally:
        await telegram.close()
        await egr.close()


def main() -> None:
    asyncio.run(run_polling())


if __name__ == "__main__":
    main()
