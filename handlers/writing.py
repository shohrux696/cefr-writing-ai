"""Single-task submissions: TASK 1.1, TASK 1.2, TASK 2 and FULL WRITING TOPSHIRISH."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import database
from config import TASKS
from handlers.common import delete_quietly, send_long_text
from keyboards.menus import (
    BTN_FULL_SUBMISSION,
    BTN_TASK_11,
    BTN_TASK_12,
    BTN_TASK_2,
    MAIN_MENU_BUTTONS,
    cancel_keyboard,
    main_menu_keyboard,
)
from services.evaluation_service import (
    EvaluationError,
    evaluate_and_store,
    format_result_text,
    get_user_lock,
    task_title,
)
from services.gemini_service import is_configured
from utils.validators import validate_writing

logger = logging.getLogger(__name__)

router = Router(name="writing")

CB_PICK_PREFIX = "pick:"


class WritingState(StatesGroup):
    waiting_text = State()


async def _enter_writing(message: Message, state: FSMContext, task_key: str) -> None:
    """Show the task instructions and wait for the student's text."""
    await state.clear()

    if not await database.is_task_enabled(task_key):
        await message.answer(
            "Bu topshiriq hozircha administrator tomonidan o'chirilgan.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if not is_configured():
        await message.answer(
            "AI baholash hozircha sozlanmagan. Administrator bilan bog'laning.",
            reply_markup=main_menu_keyboard(),
        )
        return

    spec = TASKS[task_key]
    await state.set_state(WritingState.waiting_text)
    await state.update_data(task_key=task_key)
    await message.answer(
        f"📝 {spec.title}\n\n"
        f"{spec.instructions}\n\n"
        f"🔢 Tavsiya etilgan so'zlar soni: {spec.target_min_words}–{spec.target_max_words}\n\n"
        "Javobingizni bitta xabarda yuboring.",
        reply_markup=cancel_keyboard(),
    )


@router.message(F.text == BTN_TASK_11)
async def on_task_11(message: Message, state: FSMContext) -> None:
    await _enter_writing(message, state, "task_11")


@router.message(F.text == BTN_TASK_12)
async def on_task_12(message: Message, state: FSMContext) -> None:
    await _enter_writing(message, state, "task_12")


@router.message(F.text == BTN_TASK_2)
async def on_task_2(message: Message, state: FSMContext) -> None:
    await _enter_writing(message, state, "task_2")


@router.message(F.text == BTN_FULL_SUBMISSION)
async def on_full_submission(message: Message, state: FSMContext) -> None:
    await state.clear()
    rows: list[list[InlineKeyboardButton]] = []
    for key, spec in TASKS.items():
        if await database.is_task_enabled(key):
            rows.append([InlineKeyboardButton(text=spec.title, callback_data=f"{CB_PICK_PREFIX}{key}")])

    if not rows:
        await message.answer(
            "Hozircha faol topshiriqlar yo'q. Administrator bilan bog'laning.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(
        "Qaysi topshiriq uchun matn yuborasiz? Avval topshiriq turini tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith(CB_PICK_PREFIX))
async def on_pick_task(callback: CallbackQuery, state: FSMContext) -> None:
    task_key = (callback.data or "")[len(CB_PICK_PREFIX):]
    if task_key not in TASKS:
        await callback.answer("Noma'lum topshiriq.", show_alert=True)
        return
    await callback.answer()
    if callback.message is None:
        return
    await _enter_writing(callback.message, state, task_key)


@router.message(StateFilter(WritingState.waiting_text), F.text, ~F.text.in_(MAIN_MENU_BUTTONS))
async def on_writing_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    task_key = data.get("task_key")
    if task_key not in TASKS:
        await state.clear()
        await message.answer(
            "Topshiriq topilmadi. Iltimos, menyudan qayta tanlang.",
            reply_markup=main_menu_keyboard(),
        )
        return

    validation = validate_writing(message.text)
    if not validation.is_valid:
        await message.answer(
            validation.error_message or "Matn noto'g'ri.",
            reply_markup=cancel_keyboard(),
        )
        return

    user_id = message.from_user.id
    lock = get_user_lock(user_id)
    if lock.locked():
        await message.answer("Oldingi matningiz hali baholanmoqda. Iltimos, kuting.")
        return

    async with lock:
        status = await message.answer(
            "⏳ Matningiz baholanmoqda. Bu bir necha soniya vaqt olishi mumkin..."
        )
        try:
            _, result = await evaluate_and_store(
                telegram_id=user_id,
                task_key=task_key,
                text=validation.cleaned_text,
                word_count=validation.word_count,
            )
        except EvaluationError as exc:
            await delete_quietly(status)
            await message.answer(
                f"{exc}\n\nMatningiz saqlandi. Qayta urinib ko'rishingiz mumkin.",
                reply_markup=cancel_keyboard(),
            )
            return
        except Exception:
            logger.exception("Unexpected error while evaluating writing for user %s", user_id)
            await delete_quietly(status)
            await message.answer(
                "Kutilmagan xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.",
                reply_markup=cancel_keyboard(),
            )
            return

    await delete_quietly(status)
    await state.clear()
    await send_long_text(
        message.bot,
        message.chat.id,
        format_result_text(task_title(task_key), result),
        main_menu_keyboard(),
    )


@router.message(StateFilter(WritingState.waiting_text), ~F.text)
async def on_writing_non_text(message: Message, state: FSMContext) -> None:
    await message.answer(
        "Iltimos, faqat matn yuboring.",
        reply_markup=cancel_keyboard(),
    )
