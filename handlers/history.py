"""Student history, submission details and personal statistics."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database
from config import OVERALL_MAX_SCORE, SOURCE_MOCK
from handlers.common import TASK_SHORT, format_local, send_long_text
from keyboards.menus import (
    BTN_HISTORY,
    BTN_STATS,
    CB_HISTORY_PREFIX,
    history_keyboard,
    main_menu_keyboard,
)
from services.evaluation_service import format_result_text, load_stored_result, task_title

router = Router(name="history")


@router.message(F.text == BTN_HISTORY)
async def on_history(message: Message, state: FSMContext) -> None:
    await state.clear()
    rows = await database.get_user_history(message.from_user.id, limit=10)
    if not rows:
        await message.answer(
            "Sizda hali baholangan topshiriqlar yo'q.",
            reply_markup=main_menu_keyboard(),
        )
        return

    items: list[tuple[int, str]] = []
    for row in rows:
        short = TASK_SHORT.get(row["task_type"], row["task_type"])
        cefr = row["estimated_cefr"] or "—"
        score = row["overall_score"] if row["overall_score"] is not None else "—"
        mock_marker = " (mock)" if row["source"] == SOURCE_MOCK else ""
        items.append((row["id"], f"#{row['id']} {short}{mock_marker} · {cefr} · {score}"))

    await message.answer(
        "📜 So'nggi topshiriqlaringiz. Batafsil ko'rish uchun tanlang:",
        reply_markup=history_keyboard(items),
    )


@router.callback_query(F.data.startswith(CB_HISTORY_PREFIX))
async def on_history_detail(callback: CallbackQuery) -> None:
    raw_id = (callback.data or "")[len(CB_HISTORY_PREFIX):]
    try:
        submission_id = int(raw_id)
    except ValueError:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    await callback.answer()
    telegram_id = callback.from_user.id
    detail = await database.get_submission_detail(submission_id, telegram_id)
    if detail is None:
        await callback.bot.send_message(telegram_id, "Topshiriq topilmadi.")
        return

    result = load_stored_result(detail["result_json"])
    if result is None:
        await callback.bot.send_message(
            telegram_id,
            "Bu topshiriq hali baholanmagan.",
            reply_markup=main_menu_keyboard(),
        )
        return

    title = f"{task_title(detail['task_type'])} — {format_local(detail['created_at'])}"
    await send_long_text(
        callback.bot,
        telegram_id,
        format_result_text(title, result),
        main_menu_keyboard(),
    )


@router.message(F.text == BTN_STATS)
async def on_stats(message: Message, state: FSMContext) -> None:
    await state.clear()
    stats = await database.get_user_stats(message.from_user.id)
    average = stats["average_score"]
    average_text = f"{average}/{OVERALL_MAX_SCORE}" if average is not None else "—"
    text = (
        "📊 SIZNING STATISTIKANGIZ\n\n"
        f"📝 Jami topshiriqlar: {stats['total']}\n"
        f"📈 O'rtacha ball (taxminiy): {average_text}\n"
        f"🎯 Oxirgi CEFR (taxminiy): {stats['latest_cefr'] or '—'}\n\n"
        "⚠️ Natijalar taxminiy mashq baholari. Ular rasmiy CEFR imtihon natijasi emas."
    )
    await message.answer(text, reply_markup=main_menu_keyboard())
