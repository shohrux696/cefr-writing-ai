"""Keyboards and callback constants used by the bot."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

# Main menu buttons (reply keyboard). The first one is shown prominently on its own row.
BTN_FULL_SUBMISSION = "FULL WRITING TOPSHIRISH"
BTN_TASK_11 = "TASK 1.1"
BTN_TASK_12 = "TASK 1.2"
BTN_MOCK = "FULL MOCK TEST"
BTN_TASK_2 = "TASK 2"
BTN_HISTORY = "📜 Tarix"
BTN_STATS = "📊 Statistika"
BTN_CANCEL = "❌ Bekor qilish"

MAIN_MENU_BUTTONS: tuple[str, ...] = (
    BTN_FULL_SUBMISSION,
    BTN_TASK_11,
    BTN_TASK_12,
    BTN_MOCK,
    BTN_TASK_2,
    BTN_HISTORY,
    BTN_STATS,
    BTN_CANCEL,
)

# Callback data (inline buttons)
CB_MOCK_START = "mock:start"
CB_MOCK_CANCEL = "mock:cancel"
CB_HISTORY_PREFIX = "hist:"
CB_ADMIN_STATS = "adm:stats"
CB_ADMIN_RECENT = "adm:recent"
CB_ADMIN_TASKS = "adm:tasks"
CB_ADMIN_MINUTES = "adm:minutes"
CB_ADMIN_TOGGLE_PREFIX = "adm:toggle:"
CB_ADMIN_MINUTES_PREFIX = "adm:min:"
CB_ADMIN_BACK = "adm:back"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_FULL_SUBMISSION)],
            [KeyboardButton(text=BTN_TASK_11), KeyboardButton(text=BTN_TASK_12)],
            [KeyboardButton(text=BTN_MOCK), KeyboardButton(text=BTN_TASK_2)],
            [KeyboardButton(text=BTN_HISTORY), KeyboardButton(text=BTN_STATS)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Bo'limni tanlang...",
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
        input_field_placeholder="Matningizni yuboring yoki bekor qiling",
    )


def mock_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Boshlash", callback_data=CB_MOCK_START)],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=CB_MOCK_CANCEL)],
        ]
    )


def history_keyboard(items: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    """items: list of (submission_id, button_label)."""
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"{CB_HISTORY_PREFIX}{submission_id}")]
        for submission_id, label in items
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Bot statistikasi", callback_data=CB_ADMIN_STATS)],
            [InlineKeyboardButton(text="🕒 So'nggi topshiriqlar", callback_data=CB_ADMIN_RECENT)],
            [InlineKeyboardButton(text="🔀 Vazifalarni yoqish/o'chirish", callback_data=CB_ADMIN_TASKS)],
            [InlineKeyboardButton(text="⏱ Mock test vaqtini sozlash", callback_data=CB_ADMIN_MINUTES)],
        ]
    )


def admin_tasks_keyboard(items: list[tuple[str, str, bool]]) -> InlineKeyboardMarkup:
    """items: list of (task_key, title, enabled)."""
    rows = []
    for task_key, title, enabled in items:
        marker = "✅" if enabled else "⛔"
        rows.append(
            [InlineKeyboardButton(
                text=f"{marker} {title}",
                callback_data=f"{CB_ADMIN_TOGGLE_PREFIX}{task_key}",
            )]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=CB_ADMIN_BACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_minutes_keyboard(items: list[tuple[str, str, int]]) -> InlineKeyboardMarkup:
    """items: list of (task_key, title, current_minutes)."""
    rows = []
    for task_key, title, minutes in items:
        rows.append(
            [InlineKeyboardButton(
                text=f"{title} — {minutes} daqiqa",
                callback_data=f"{CB_ADMIN_MINUTES_PREFIX}{task_key}",
            )]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=CB_ADMIN_BACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Admin menyu", callback_data=CB_ADMIN_BACK)]]
    )
