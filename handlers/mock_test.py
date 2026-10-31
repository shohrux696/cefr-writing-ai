"""FULL MOCK TEST: timed writing exam with saved answers and a final report.

Flow:
1. The student starts the mock test; a session with all enabled tasks is created.
2. The first task opens and gets a deadline (set by the administrator).
3. The student sends the answer. The task closes, the next task opens,
   and the answer is evaluated.
4. If a deadline passes, the task closes automatically and the next task opens.
5. After the last task, the final report is sent.

While a mock test is active, menu buttons are blocked. Only the cancel button,
/time, and /start, /help commands work.
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import database
from config import MOCK_TASK_ORDER, SOURCE_MOCK, TASKS
from handlers.common import delete_quietly, safe_edit_text, send_long_text
from keyboards.menus import (
    BTN_CANCEL,
    BTN_MOCK,
    CB_MOCK_CANCEL,
    CB_MOCK_START,
    MAIN_MENU_BUTTONS,
    cancel_keyboard,
    main_menu_keyboard,
    mock_start_keyboard,
)
from services import timer_service
from services.evaluation_service import (
    EvaluationError,
    evaluate_text,
    format_result_text,
    get_user_lock,
    load_stored_result,
    task_title,
)
from services.gemini_service import is_configured
from services.timer_service import cancel_timer, format_seconds, schedule_expiry, seconds_left
from utils.validators import validate_writing

logger = logging.getLogger(__name__)

router = Router(name="mock_test")

STATUS_UZ: dict[str, str] = {
    "waiting": "boshlanmagan",
    "open": "to'xtatildi",
    "submitted": "topshirildi",
    "expired": "vaqt tugadi",
}


class ActiveMockFilter(BaseFilter):
    """True when the student has an active mock test session."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        if user is None:
            return False
        return await database.get_active_mock_session(user.id) is not None


def _task_text(task_key: str, position: int, total: int, deadline_iso: str) -> str:
    spec = TASKS[task_key]
    remaining = format_seconds(seconds_left(deadline_iso))
    return (
        f"🧪 FULL MOCK TEST — {position + 1}/{total}\n\n"
        f"📝 {spec.title}\n\n"
        f"{spec.instructions}\n\n"
        f"🔢 Tavsiya etilgan so'zlar: {spec.target_min_words}–{spec.target_max_words}\n"
        f"⏱ Qolgan vaqt: {remaining}\n\n"
        "Javobingizni bitta xabarda yuboring. Yuborilgach topshiriq yopiladi "
        "va uni o'zgartirib bo'lmaydi."
    )


async def _open_next_and_schedule(bot: Bot, telegram_id: int, session_id: int) -> bool:
    """Open the next waiting task and start its timer.

    Returns False when no tasks are left. In that case the session is finished
    and the caller must send the final report.
    """
    opened = await database.open_next_mock_task(session_id)
    if opened is None:
        await database.finish_mock_session(session_id)
        return False

    schedule_expiry(
        task_id=opened["id"],
        session_id=session_id,
        telegram_id=telegram_id,
        deadline_iso=opened["deadline_at"],
    )
    tasks = await database.get_mock_tasks(session_id)
    await bot.send_message(
        chat_id=telegram_id,
        text=_task_text(opened["task_type"], opened["position"], len(tasks), opened["deadline_at"]),
        reply_markup=cancel_keyboard(),
    )
    return True


async def send_final_report(bot: Bot, telegram_id: int, session_id: int) -> None:
    """Send the summary of all tasks of one mock test session."""
    tasks = await database.get_mock_tasks(session_id)
    answers = {
        row["mock_task_id"]: row
        for row in await database.get_mock_answers(session_id)
    }

    lines: list[str] = [
        "🏁 FULL MOCK TEST NATIJALARI",
        "Bu natijalar taxminiy mashq baholari. Ular rasmiy imtihon natijasi emas.",
        "",
    ]
    scores: list[int] = []

    for task in tasks:
        title = task_title(task["task_type"])
        lines.append(f"{task['position'] + 1}. {title}")
        answer = answers.get(task["id"])
        if answer is None:
            status = STATUS_UZ.get(task["status"], task["status"])
            lines.append(f"   Holat: {status}")
            lines.append("")
            continue

        lines.append(f"   So'zlar soni: {answer['word_count']}")
        result = None
        if answer["submission_id"] is not None:
            detail = await database.get_submission_detail(answer["submission_id"], telegram_id)
            if detail is not None:
                result = load_stored_result(detail["result_json"])

        if result is None:
            lines.append("   Baholash natijasi mavjud emas.")
        else:
            scores.append(int(result["overall_score"]))
            lines.append(f"   CEFR (taxminiy): {result['estimated_cefr_level']}")
            lines.append(f"   Ball (taxminiy): {result['overall_score']}")
        lines.append("")

    if scores:
        average = round(sum(scores) / len(scores), 1)
        lines.append(f"📈 O'rtacha ball (taxminiy): {average}")
    lines.append("Batafsil natijalarni 📜 Tarix bo'limida ko'rishingiz mumkin.")

    await send_long_text(bot, telegram_id, "\n".join(lines), main_menu_keyboard())


async def _evaluate_mock_answer(
    bot: Bot,
    telegram_id: int,
    session_id: int,
    task_row,
    text: str,
    word_count: int,
) -> None:
    """Evaluate one submitted mock answer and send the feedback to the student."""
    task_key = task_row["task_type"]
    task_id = task_row["id"]
    status = await bot.send_message(telegram_id, "⏳ Javobingiz baholanmoqda...")

    result = None
    error_text: str | None = None
    try:
        submission_id = await database.create_submission(
            telegram_id=telegram_id,
            task_type=task_key,
            original_text=text,
            word_count=word_count,
            source=SOURCE_MOCK,
            mock_session_id=session_id,
        )
        await database.attach_submission_to_mock_answer(task_id, submission_id)
        result = await evaluate_text(task_key, text, word_count)
        await database.save_evaluation(
            submission_id=submission_id,
            estimated_cefr=result["estimated_cefr_level"],
            overall_score=result["overall_score"],
            result=result,
        )
    except EvaluationError as exc:
        error_text = f"Bu topshiriq baholanmadi: {exc}\nJavobingiz saqlandi va yakuniy hisobotda ko'rinadi."
    except Exception:
        logger.exception("Unexpected error while evaluating mock task %s", task_id)
        error_text = "Kutilmagan xatolik yuz berdi. Javobingiz saqlandi."

    await delete_quietly(status)
    if error_text is not None or result is None:
        await bot.send_message(telegram_id, error_text or "Baholash natijasi bo'sh.")
        return

    await send_long_text(
        bot,
        telegram_id,
        format_result_text(f"{task_title(task_key)} (FULL MOCK TEST)", result),
    )


def build_expiry_handler(bot: Bot):
    """Create the function that runs when a task time expires."""

    async def handle_expiry(telegram_id: int, session_id: int, task_id: int) -> None:
        expired = await database.expire_mock_task(task_id)
        if not expired:
            return
        await bot.send_message(
            telegram_id,
            "⏰ Vaqt tugadi. Bu topshiriq uchun yozilgan matn saqlanmadi, chunki yuborilmagan edi.",
        )
        has_next = await _open_next_and_schedule(bot, telegram_id, session_id)
        if not has_next:
            await send_final_report(bot, telegram_id, session_id)

    return handle_expiry


def setup_mock_timers(bot: Bot) -> None:
    """Connect the timer service to the expiry handler. Call once at startup."""
    timer_service.set_expiry_handler(build_expiry_handler(bot))


# ---------------------------------------------------------------------------
# Start, overview and status
# ---------------------------------------------------------------------------

@router.message(F.text == BTN_CANCEL, ActiveMockFilter())
async def on_mock_cancel(message: Message, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    session = await database.get_active_mock_session(telegram_id)
    if session is None:
        return
    await state.clear()

    open_task = await database.get_open_mock_task(session["id"])
    if open_task is not None:
        cancel_timer(open_task["id"])
    await database.finish_mock_session(session["id"])

    await message.answer("🛑 Mock test to'xtatildi. Yuborilgan javoblar saqlangan.")
    await send_final_report(message.bot, telegram_id, session["id"])


@router.message(ActiveMockFilter(), F.text.in_(MAIN_MENU_BUTTONS))
async def on_mock_blocked_menu(message: Message) -> None:
    await message.answer(
        "⏳ Mock test davom etmoqda. Uni yakunlaguncha boshqa bo'limlar ishlamaydi.\n"
        "Qolgan vaqtni /time bilan ko'rishingiz mumkin. Bekor qilish uchun ❌ tugmasini bosing."
    )


@router.message(Command("time"), ActiveMockFilter())
async def on_mock_time(message: Message) -> None:
    session = await database.get_active_mock_session(message.from_user.id)
    if session is None:
        return
    open_task = await database.get_open_mock_task(session["id"])
    if open_task is None:
        await message.answer("Hozir faol topshiriq yo'q.")
        return
    remaining = format_seconds(seconds_left(open_task["deadline_at"]))
    await message.answer(f"⏱ Qolgan vaqt: {remaining}")


@router.message(ActiveMockFilter(), F.text, ~F.text.startswith("/"))
async def on_mock_answer(message: Message, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    session = await database.get_active_mock_session(telegram_id)
    if session is None:
        return
    open_task = await database.get_open_mock_task(session["id"])
    if open_task is None:
        await message.answer("Hozir faol topshiriq yo'q. Keyingi topshiriq ochilishini kuting.")
        return

    validation = validate_writing(message.text)
    if not validation.is_valid:
        await message.answer(validation.error_message or "Matn noto'g'ri.")
        return

    lock = get_user_lock(telegram_id)
    if lock.locked():
        await message.answer("Oldingi javobingiz hali baholanmoqda. Iltimos, kuting.")
        return

    async with lock:
        submitted = await database.submit_mock_answer(
            task_id=open_task["id"],
            session_id=session["id"],
            task_type=open_task["task_type"],
            answer_text=validation.cleaned_text,
            word_count=validation.word_count,
        )
        if not submitted:
            await message.answer("Bu topshiriq allaqachon yopilgan.")
            return

        cancel_timer(open_task["id"])
        has_next = await _open_next_and_schedule(message.bot, telegram_id, session["id"])
        await _evaluate_mock_answer(
            message.bot,
            telegram_id,
            session["id"],
            open_task,
            validation.cleaned_text,
            validation.word_count,
        )
        if not has_next:
            await send_final_report(message.bot, telegram_id, session["id"])


@router.message(ActiveMockFilter(), ~F.text)
async def on_mock_non_text(message: Message) -> None:
    await message.answer("Iltimos, faqat matn yuboring.")


@router.message(F.text == BTN_MOCK)
async def on_mock_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    task_keys = [key for key in MOCK_TASK_ORDER if await database.is_task_enabled(key)]
    if not task_keys:
        await message.answer(
            "Hozircha mock test uchun faol topshiriqlar yo'q. Administrator bilan bog'laning.",
            reply_markup=main_menu_keyboard(),
        )
        return
    if not is_configured():
        await message.answer(
            "AI baholash hozircha sozlanmagan. Administrator bilan bog'laning.",
            reply_markup=main_menu_keyboard(),
        )
        return

    lines: list[str] = [
        "🧪 FULL MOCK TEST",
        "",
        "Topshiriqlar ketma-ket beriladi. Har biri uchun vaqt cheklangan:",
    ]
    for key in task_keys:
        minutes = await database.get_task_minutes(key)
        lines.append(f"• {TASKS[key].title} — {minutes} daqiqa")
    lines += [
        "",
        "⚠️ Vaqt tugagach topshiriq avtomatik yopiladi. Yuborilmagan matn saqlanmaydi.",
        "Yuborilgan javobni o'zgartirib bo'lmaydi.",
        "",
        "Vaqt sozlamalari administrator tomonidan belgilanadi. Bu rasmiy imtihon vaqti emas.",
    ]
    await message.answer("\n".join(lines), reply_markup=mock_start_keyboard())


@router.callback_query(F.data == CB_MOCK_START)
async def on_mock_start(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    await state.clear()

    if not is_configured():
        await callback.answer("AI baholash sozlanmagan.", show_alert=True)
        return

    task_keys = [key for key in MOCK_TASK_ORDER if await database.is_task_enabled(key)]
    if not task_keys:
        await callback.answer("Hozircha faol topshiriqlar yo'q.", show_alert=True)
        return

    async with get_user_lock(user_id):
        if await database.get_active_mock_session(user_id) is not None:
            await callback.answer("Sizda faol mock test bor.", show_alert=True)
            return
        session_id = await database.create_mock_session(user_id, task_keys)

    await callback.answer()
    if callback.message is not None:
        await safe_edit_text(callback.message, "✅ Mock test boshlandi. Topshiriqlar quyida.", None)
    await _open_next_and_schedule(callback.bot, user_id, session_id)


@router.callback_query(F.data == CB_MOCK_CANCEL)
async def on_mock_start_cancel(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is not None:
        await safe_edit_text(callback.message, "❌ Mock test bekor qilindi.", None)


# Keep InlineKeyboardMarkup imported for type checkers that inspect this module
_ = InlineKeyboardMarkup
