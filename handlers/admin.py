"""Administrator panel. Only the user whose ID equals ADMIN_ID can use it."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import database
from config import ADMIN_ID, TASKS
from handlers.common import TASK_SHORT, format_local, safe_edit_text
from keyboards.menus import (
    CB_ADMIN_BACK,
    CB_ADMIN_MINUTES,
    CB_ADMIN_MINUTES_PREFIX,
    CB_ADMIN_RECENT,
    CB_ADMIN_STATS,
    CB_ADMIN_TASKS,
    CB_ADMIN_TOGGLE_PREFIX,
    MAIN_MENU_BUTTONS,
    admin_main_keyboard,
    admin_minutes_keyboard,
    admin_tasks_keyboard,
)
from utils.validators import parse_positive_int


class IsAdmin(BaseFilter):
    """Allows a message or callback only from the configured administrator."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return bool(user) and ADMIN_ID > 0 and user.id == ADMIN_ID


class AdminState(StatesGroup):
    waiting_minutes = State()


router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

MINUTES_MIN = 1
MINUTES_MAX = 240


def _display_name(row) -> str:
    if row["first_name"]:
        return row["first_name"]
    if row["username"]:
        return f"@{row['username']}"
    return str(row["telegram_id"])


async def _show(callback: CallbackQuery, text: str, markup) -> None:
    await callback.answer()
    if callback.message is None:
        await callback.bot.send_message(callback.from_user.id, text, reply_markup=markup)
        return
    await safe_edit_text(callback.message, text, markup)


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🛠 ADMIN PANEL", reply_markup=admin_main_keyboard())


@router.callback_query(F.data == CB_ADMIN_STATS)
async def on_admin_stats(callback: CallbackQuery) -> None:
    stats = await database.get_bot_statistics()
    average = stats["average_score"] if stats["average_score"] is not None else "—"
    text = (
        "📊 BOT STATISTIKASI\n\n"
        f"👥 Jami foydalanuvchilar: {stats['total_users']}\n"
        f"🟢 Faol (oxirgi 7 kun): {stats['active_users_7d']}\n"
        f"📝 Jami topshiriqlar: {stats['total_submissions']}\n"
        f"✅ Baholangan topshiriqlar: {stats['evaluated_submissions']}\n"
        f"🧪 Yakunlangan mock testlar: {stats['finished_mock_tests']}\n"
        f"📈 O'rtacha ball (taxminiy): {average}"
    )
    await _show(callback, text, admin_main_keyboard())


@router.callback_query(F.data == CB_ADMIN_RECENT)
async def on_admin_recent(callback: CallbackQuery) -> None:
    rows = await database.get_recent_submissions(limit=10)
    if not rows:
        await _show(callback, "Hali topshiriqlar yo'q.", admin_main_keyboard())
        return

    lines = ["🕒 SO'NGGI TOPSHIRIQLAR (oxirgi 10 ta)", ""]
    for row in rows:
        short = TASK_SHORT.get(row["task_type"], row["task_type"])
        source = "mock" if row["source"] == "mock" else "single"
        lines.append(
            f"{format_local(row['created_at'])} | {_display_name(row)} | "
            f"{short} ({source}) | {row['estimated_cefr'] or '—'} | {row['overall_score'] if row['overall_score'] is not None else '—'}"
        )
    await _show(callback, "\n".join(lines), admin_main_keyboard())


@router.callback_query(F.data == CB_ADMIN_TASKS)
async def on_admin_tasks(callback: CallbackQuery) -> None:
    items = []
    for key, spec in TASKS.items():
        items.append((key, spec.title, await database.is_task_enabled(key)))
    await _show(
        callback,
        "🔀 Topshiriqni yoqish yoki o'chirish uchun bosing:\n✅ yoqilgan, ⛔ o'chirilgan",
        admin_tasks_keyboard(items),
    )


@router.callback_query(F.data.startswith(CB_ADMIN_TOGGLE_PREFIX))
async def on_admin_toggle(callback: CallbackQuery) -> None:
    task_key = (callback.data or "")[len(CB_ADMIN_TOGGLE_PREFIX):]
    if task_key not in TASKS:
        await callback.answer("Noma'lum topshiriq.", show_alert=True)
        return
    currently_enabled = await database.is_task_enabled(task_key)
    await database.set_task_enabled(task_key, not currently_enabled)

    items = []
    for key, spec in TASKS.items():
        items.append((key, spec.title, await database.is_task_enabled(key)))
    await _show(
        callback,
        "🔀 Topshiriqni yoqish yoki o'chirish uchun bosing:\n✅ yoqilgan, ⛔ o'chirilgan",
        admin_tasks_keyboard(items),
    )


@router.callback_query(F.data == CB_ADMIN_MINUTES)
async def on_admin_minutes(callback: CallbackQuery) -> None:
    items = []
    for key, spec in TASKS.items():
        items.append((key, spec.title, await database.get_task_minutes(key)))
    await _show(
        callback,
        "⏱ Mock test vaqtini o'zgartirish uchun topshiriqni tanlang.\n"
        "Bu vaqtlar standart mashq qiymatlari, rasmiy imtihon vaqti emas.",
        admin_minutes_keyboard(items),
    )


@router.callback_query(F.data.startswith(CB_ADMIN_MINUTES_PREFIX))
async def on_admin_minutes_pick(callback: CallbackQuery, state: FSMContext) -> None:
    task_key = (callback.data or "")[len(CB_ADMIN_MINUTES_PREFIX):]
    if task_key not in TASKS:
        await callback.answer("Noma'lum topshiriq.", show_alert=True)
        return
    await state.set_state(AdminState.waiting_minutes)
    await state.update_data(task_key=task_key)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            f"{TASKS[task_key].title} uchun yangi vaqtni daqiqada yozing "
            f"({MINUTES_MIN} dan {MINUTES_MAX} gacha butun son):"
        )


@router.message(StateFilter(AdminState.waiting_minutes), F.text, ~F.text.in_(MAIN_MENU_BUTTONS))
async def on_admin_minutes_input(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    task_key = data.get("task_key")
    if task_key not in TASKS:
        await state.clear()
        await message.answer("Topshiriq topilmadi. Admin menyuga qayting.", reply_markup=admin_main_keyboard())
        return

    minutes = parse_positive_int(message.text, MINUTES_MIN, MINUTES_MAX)
    if minutes is None:
        await message.answer(
            f"Iltimos, {MINUTES_MIN} dan {MINUTES_MAX} gacha butun son yozing."
        )
        return

    await database.set_task_minutes(task_key, minutes)
    await state.clear()
    await message.answer(
        f"✅ {TASKS[task_key].title}: {minutes} daqiqa saqlandi.",
        reply_markup=admin_main_keyboard(),
    )


@router.callback_query(F.data == CB_ADMIN_BACK)
async def on_admin_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _show(callback, "🛠 ADMIN PANEL", admin_main_keyboard())
