"""Application entry point. Start the bot with: python main.py"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import Bot, BaseMiddleware, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent, Message, TelegramObject

import database
from config import BOT_TOKEN, ConfigError, setup_logging, validate_config
from handlers import admin, history, mock_test, start, writing
from handlers.mock_test import setup_mock_timers
from services import question_service, timer_service

logger = logging.getLogger(__name__)


class UserTrackingMiddleware(BaseMiddleware):
    """Save or update the user's Telegram profile on every message and button press."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None and not user.is_bot:
            try:
                await database.upsert_user(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                )
            except Exception:
                logger.exception("Could not save user %s", user.id)
        return await handler(event, data)


async def on_error(event: ErrorEvent) -> bool:
    """Log every unhandled error and tell the student, so one failure never stops the bot."""
    logger.exception("Unhandled error while processing an update", exc_info=event.exception)
    try:
        inner = event.update.event
        target = getattr(inner, "message", None) or inner
        if isinstance(target, Message):
            await target.answer(
                "Kutilmagan xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring."
            )
    except Exception:
        logger.exception("Could not send the error message to the user")
    return True


async def main() -> int:
    setup_logging()
    try:
        validate_config()
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        print(f"Sozlamalarda xatolik: {exc}")
        print("Iltimos, .env faylini tekshiring (.env.example ga qarang).")
        return 1

    await database.init_db()
    await question_service.init_question_bank()

    bot = Bot(token=BOT_TOKEN)
    dispatcher = Dispatcher(storage=MemoryStorage())

    dispatcher.message.outer_middleware(UserTrackingMiddleware())
    dispatcher.callback_query.outer_middleware(UserTrackingMiddleware())
    dispatcher.errors.register(on_error)

    # Order matters: admin and mock test handlers must be checked before the
    # general menu handlers, and the fallback must be last.
    dispatcher.include_router(admin.router)
    dispatcher.include_router(mock_test.router)
    dispatcher.include_router(writing.router)
    dispatcher.include_router(history.router)
    dispatcher.include_router(start.router)
    dispatcher.include_router(start.fallback_router)

    setup_mock_timers(bot)
    restored = await timer_service.restore_timers()
    logger.info("Bot starting. Restored mock timers: %d", restored)

    try:
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        timer_service.cancel_all_timers()
        await bot.session.close()
        logger.info("Bot stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
