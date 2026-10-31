"""/start, /help, /cancel, cancel button and the fallback for unexpected messages."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards.menus import BTN_CANCEL, main_menu_keyboard

logger = logging.getLogger(__name__)

router = Router(name="start")
fallback_router = Router(name="fallback")

WELCOME_TEXT = (
    "👋 Assalomu alaykum!\n\n"
    "CEFR Writing Checker botiga xush kelibsiz.\n"
    "Bu bot ingliz tilidagi yozma ishlaringizni AI yordamida baholaydi: "
    "xatolarni topadi, ularni Uzbek tilida tushuntiradi, taxminiy CEFR darajasini "
    "va ballni ko'rsatadi.\n\n"
    "Quyidagi menyudan kerakli bo'limni tanlang."
)

HELP_TEXT = (
    "ℹ️ YORDAM\n\n"
    "📝 FULL WRITING TOPSHIRISH: topshiriq turini tanlab, matningizni yuborasiz.\n"
    "📝 TASK 1.1: norasmiy (informal) email, taxminan 50 so'z.\n"
    "📝 TASK 1.2: rasmiy (formal) email, 120–150 so'z.\n"
    "📝 TASK 2: blog post yoki fikr-mulohaza, 180–200 so'z.\n"
    "🧪 FULL MOCK TEST: vaqt cheklangan imtihon rejimi. Topshiriqlar ketma-ket beriladi.\n"
    "📜 Tarix: oldingi natijalaringiz.\n"
    "📊 Statistika: umumiy ko'rsatkichlaringiz.\n\n"
    "Buyruqlar:\n"
    "/start — botni qayta boshlash\n"
    "/help — yordam\n"
    "/cancel — joriy amalni bekor qilish\n\n"
    "⚠️ AI bahosi taxminiy mashq bahosi. U rasmiy CEFR imtihon natijasi emas."
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(HELP_TEXT, reply_markup=main_menu_keyboard())


@router.message(Command("cancel"))
@router.message(F.text == BTN_CANCEL)
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("✅ Joriy amal bekor qilindi.", reply_markup=main_menu_keyboard())


@fallback_router.message()
async def on_unexpected_message(message: Message, state: FSMContext) -> None:
    await message.answer(
        "Tushunmadim. Iltimos, quyidagi menyudan tanlang yoki /help buyrug'ini yuboring.",
        reply_markup=main_menu_keyboard(),
    )


@fallback_router.callback_query()
async def on_stale_callback(callback: CallbackQuery) -> None:
    await callback.answer("Bu tugma eskirgan. Qaytadan urinib ko'ring.")
