"""Helpers shared by several handler modules."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Union
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup, Message, ReplyKeyboardMarkup

from services.evaluation_service import split_for_telegram

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("Asia/Tashkent")
TASK_SHORT: dict[str, str] = {"task_11": "1.1", "task_12": "1.2", "task_2": "2"}

Markup = Union[ReplyKeyboardMarkup, InlineKeyboardMarkup, None]


async def send_long_text(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: Markup = None,
) -> None:
    """Send a long text in several Telegram messages. The keyboard is attached to the last part."""
    chunks = split_for_telegram(text)
    last_index = len(chunks) - 1
    for index, chunk in enumerate(chunks):
        await bot.send_message(
            chat_id=chat_id,
            text=chunk,
            reply_markup=reply_markup if index == last_index else None,
        )


async def delete_quietly(message: Message | None) -> None:
    """Delete a message, ignoring Telegram errors (for example, if it is already gone)."""
    if message is None:
        return
    try:
        await message.delete()
    except TelegramAPIError:
        pass


async def safe_edit_text(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Edit a message. If editing fails, send a new message instead."""
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramAPIError:
        await message.answer(text, reply_markup=reply_markup)


def format_local(iso_value: str | None) -> str:
    """Convert a stored UTC ISO timestamp to Tashkent local time for display."""
    if not iso_value:
        return "—"
    try:
        value = datetime.fromisoformat(iso_value)
    except ValueError:
        return iso_value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(LOCAL_TZ).strftime("%d.%m.%Y %H:%M")
